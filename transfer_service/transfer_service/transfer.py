from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable

from tqdm import tqdm

from .drivers.k2182 import Keithley2182
from .drivers.dp320b import Dataproof320B
from .drivers.lte300 import LTE300
from .io.raw_csv import append_raw_csv
from .math.stats import mean, type_a_u_mean
from .math.transfer_calc import calc_delta, calc_u_dut
from .math.uncertainty import estimate_uncertainty
from .math.ne_temp import saturated_to_20c, unsaturated_to_20c_uv_per_c


@dataclass
class PolarityMap:
    plus_a: int
    plus_b: int
    minus_a: int
    minus_b: int


@dataclass
class MeasurePlan:
    cycles: int = 3
    settle_after_switch_s: float = 60.0

    # New (v0.0.8): fixed number of samples per polarity within each cycle.
    # Guarantees n_plus == n_minus.
    samples_per_polarity: int = 20

    # Delay between consecutive readings (s)
    sample_delay_s: float = 0.0

    # Legacy (<= v0.0.7): time-based block duration (s). Kept for backward compatibility.
    block_duration_s: float = 120.0

@dataclass
class CellTempModel:
    """Temperature correction model for a normal cell.

    - saturated: uses saturated_to_20c()
    - unsaturated: uses alpha_uV_per_C (µV/°C) with unsaturated_to_20c_uv_per_c()
    """
    cell_type: str = "saturated"  # 'saturated' | 'unsaturated'
    alpha_uV_per_C: Optional[float] = None

    def __post_init__(self) -> None:
        ct = (self.cell_type or "").strip().lower()
        if ct not in ("saturated", "unsaturated"):
            raise ValueError("cell_type must be 'saturated' or 'unsaturated'")
        self.cell_type = ct
        if self.cell_type == "unsaturated" and self.alpha_uV_per_C is None:
            # allow None during configuration, but measurement will raise if missing
            pass

def _acquire_samples_with_lte(
    meter: Keithley2182,
    lte: LTE300,
    n_samples: int,
    sample_delay_s: float,
    polarity: str,
    env: Optional[Dict[str, float]] = None,
) -> Tuple[List[float], List[float], List[tuple]]:
    """Acquire a fixed number of samples, logging LTE temperature for each measurement.

    Notes:
    - For real 2182 we must run DFIL OFF -> sleep -> ON before each reading (per user requirement).
    - This function therefore calls meter.dfil_cycle_before_measurement() for every sample.
    """
    values: List[float] = []
    temps: List[float] = []
    rows: List[tuple] = []

    for _ in range(int(n_samples)):
        meter.dfil_cycle_before_measurement()
        v = meter.read_fresh()
        t_lte = lte.read_temperature_c()
        ts = time.time()
        values.append(v)
        temps.append(t_lte)
        if env:
            rows.append((ts, polarity, v, t_lte, env.get("t_c"), env.get("rh_pct"), env.get("p_kpa")))
        else:
            rows.append((ts, polarity, v, t_lte, None, None, None))
        if sample_delay_s > 0:
            time.sleep(sample_delay_s)

    return values, temps, rows

def _acquire_block_with_lte(
    meter: Keithley2182,
    lte: LTE300,
    duration_s: float,
    sample_delay_s: float,
    polarity: str,
    env: Optional[Dict[str, float]] = None,
) -> Tuple[List[float], List[float], List[tuple]]:
    values: List[float] = []
    temps: List[float] = []
    rows: List[tuple] = []

    t0 = time.time()
    while (time.time() - t0) < duration_s:
        v = meter.read_fresh()
        t_lte = lte.read_temperature_c()
        ts = time.time()
        values.append(v)
        temps.append(t_lte)
        if env:
            rows.append((ts, polarity, v, t_lte, env.get("t_c"), env.get("rh_pct"), env.get("p_kpa")))
        else:
            rows.append((ts, polarity, v, t_lte, None, None, None))
        if sample_delay_s > 0:
            time.sleep(sample_delay_s)

    return values, temps, rows


def run_transfer_level(
    meter: Keithley2182,
    switch: Dataproof320B,
    lte: LTE300,
    mapping: PolarityMap,
    plan: MeasurePlan,
    level_v: float,
    u_ref_v: float,
    u_ref_std_unc_v: float,
    cell_model: CellTempModel,
    raw_csv_path: Optional[Path] = None,
    env_snapshot: Optional[Dict[str, float]] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """Run one transfer for a single REF↔DUT pair and one level.

    v0.0.8: acquisition is sample-count based (samples_per_polarity), not time based.
    v0.0.9: optional progress callback for Web UI.
    """

    def _progress(frac: float, msg: str) -> None:
        if progress_cb is None:
            return
        try:
            progress_cb(float(max(0.0, min(1.0, frac))), str(msg))
        except Exception:
            pass

    raw_plus: List[float] = []
    raw_minus: List[float] = []
    t_plus: List[float] = []
    t_minus: List[float] = []

    # Raw data for XLSX (grouped by cycle, 4 columns: +V, +LTE, -V, -LTE)
    raw_cycles: List[Dict[str, Any]] = []

    # total work units: per cycle = switch+ + samples + switch- + samples
    total_units = plan.cycles * (2 + 2 * plan.samples_per_polarity)
    done_units = 0

    def acquire(polarity: str, a_ch: int, b_ch: int, cycle_idx: int, cycle_rec: Dict[str, Any]) -> None:
        nonlocal done_units

        # Ensure scanner starts from open relays (user requirement)
        switch.open_all()

        # Switch polarity
        switch.set_pair(a_ch, b_ch)
        done_units += 1
        _progress(done_units / max(1, total_units),
                  f"Cycle {cycle_idx+1}/{plan.cycles}: change polarity {polarity} (A{a_ch:02d}, B{b_ch:02d})")

        # Allow settling after switch
        if plan.settle_after_switch_s > 0:
            time.sleep(plan.settle_after_switch_s)

        # Acquire fixed number of samples
        for k in range(int(plan.samples_per_polarity)):
            # For 2182: DFIL OFF -> wait -> ON before each reading (per requirement)
            meter.dfil_cycle_before_measurement()
            v = meter.read_fresh()
            t_lte = lte.read_temperature_c()
            ts = time.time()

            # Store raw point for report (per-sample LTE)
            if polarity == "+":
                cycle_rec["plus"].append({"value_V": v, "lte_temp_C": t_lte})
            else:
                cycle_rec["minus"].append({"value_V": v, "lte_temp_C": t_lte})

            if polarity == "+":
                raw_plus.append(v)
                t_plus.append(t_lte)
            else:
                raw_minus.append(v)
                t_minus.append(t_lte)

            # Raw CSV logging is optional (Web UI may disable it).
            # Guard against raw_csv_path=None to avoid AttributeError.
            if raw_csv_path is not None:
                append_raw_csv(
                    raw_csv_path,
                    [(ts, polarity, v, t_lte,
                      (env_snapshot or {}).get("t_c") if env_snapshot else None,
                      (env_snapshot or {}).get("rh_pct") if env_snapshot else None,
                      (env_snapshot or {}).get("p_kpa") if env_snapshot else None)]
                )

            done_units += 1
            # Do not spam: update message every 5 samples or on the last sample
            if (k % 5 == 0) or (k == plan.samples_per_polarity - 1):
                _progress(done_units / max(1, total_units),
                          f"Cycle {cycle_idx+1}/{plan.cycles}: {polarity} sample {k+1}/{plan.samples_per_polarity}")

            if plan.sample_delay_s > 0:
                time.sleep(plan.sample_delay_s)

    _progress(0.0, "Starting level measurement")

    for cycle_idx in range(int(plan.cycles)):
        cycle_rec: Dict[str, Any] = {"cycle": cycle_idx + 1, "plus": [], "minus": []}
        raw_cycles.append(cycle_rec)
        acquire("+", mapping.plus_a, mapping.plus_b, cycle_idx, cycle_rec)
        acquire("-", mapping.minus_a, mapping.minus_b, cycle_idx, cycle_rec)

    _progress(done_units / max(1, total_units), "Processing results")

    # Use paired reversal samples: delta_i = (plus_i - minus_i) / 2
    n_pairs = min(len(raw_plus), len(raw_minus))
    if n_pairs == 0:
        raise ValueError("No samples acquired")

    r_plus = mean(raw_plus[:n_pairs])
    r_minus = mean(raw_minus[:n_pairs])
    delta_samples = [(p - m) / 2.0 for p, m in zip(raw_plus[:n_pairs], raw_minus[:n_pairs])]
    delta = mean(delta_samples)

    u_dut = calc_u_dut(u_ref_v, delta)

    t_plus_mean = mean(t_plus[:n_pairs]) if t_plus else 0.0
    t_minus_mean = mean(t_minus[:n_pairs]) if t_minus else 0.0
    t_mean = mean((t_plus[:n_pairs] if t_plus else []) + (t_minus[:n_pairs] if t_minus else [])) if (t_plus or t_minus) else 0.0

    if cell_model.cell_type == "saturated":
        u20 = saturated_to_20c(u_dut, t_mean)
    elif cell_model.cell_type == "unsaturated":
        if cell_model.alpha_uV_per_C is None:
            raise ValueError("alpha_uV_per_C is required for unsaturated cell")
        u20 = unsaturated_to_20c_uv_per_c(u_dut, t_mean, cell_model.alpha_uV_per_C)
    else:
        raise ValueError("cell_type must be 'saturated' or 'unsaturated'")

    typeA_std, typeA_u = type_a_u_mean(delta_samples)
    unc = estimate_uncertainty(delta_samples, u_ref=u_ref_std_unc_v)

    _progress(1.0, "Level completed")

    return {
        "level_V": level_v,
        "u_ref_V": u_ref_v,
        "r_plus_mean_V": r_plus,
        "r_minus_mean_V": r_minus,
        "delta_V": delta,
        "u_dut_V": u_dut,
        "t_plus_mean_C": t_plus_mean,
        "t_minus_mean_C": t_minus_mean,
        "t_mean_C": t_mean,
        "u20_mean_V": u20,
        "n_plus": len(raw_plus),
        "n_minus": len(raw_minus),
        "n_pairs": int(n_pairs),
        "typeA_std_V": typeA_std,
        "typeA_u_mean_V": typeA_u,
        "u_ref_std_unc_V": u_ref_std_unc_v,
        "u_combined_V": unc.u_combined,
        "U_k2_V": unc.U_k2,
        "cell_type": cell_model.cell_type,
        "alpha_uV_per_C": cell_model.alpha_uV_per_C,
        "raw_cycles": raw_cycles,
    }
