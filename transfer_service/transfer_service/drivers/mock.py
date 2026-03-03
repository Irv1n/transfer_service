from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Optional, Callable


@dataclass
class SimConfig:
    # All voltage parameters in microvolts unless noted
    offset_uV: float = 0.0          # constant offset (µV)
    noise_rms_uV: float = 0.05      # gaussian RMS noise (µV)
    drift_uV_per_min: float = 0.0   # linear drift (µV/min)
    outlier_prob: float = 0.0       # probability per sample (0..1)
    outlier_uV: float = 1.0         # outlier amplitude (µV)

    # Temperature simulation
    temp_c: float = 23.0
    temp_noise_c: float = 0.02


class Mock320B:
    """Dataproof 320B emulator.
    Stores last A/B channel pair and provides current polarity for the meter emulator.
    """

    def __init__(self):
        self.last_a: Optional[int] = None
        self.last_b: Optional[int] = None
        self._ref_ch: Optional[int] = None
        self._dut_ch: Optional[int] = None
        self._polarity: str = "+"

    def set_pair(self, a: int, b: int) -> None:
        self.last_a, self.last_b = a, b

        # If we already know ref/dut, infer polarity by A-side
        if self._ref_ch is not None and self._dut_ch is not None:
            self._polarity = "+" if a == self._ref_ch else "-"
            return

        # Bootstrap: assume first call is PLUS (as in run_transfer_level).
        if self._ref_ch is None and self._dut_ch is None:
            self._ref_ch, self._dut_ch = a, b
            self._polarity = "+"
            return

        self._polarity = "+"

    def open_all(self) -> None:
        """Emulate A00/B00 (open all relays)."""
        self.last_a, self.last_b = None, None
        # Do not change inferred ref/dut mapping; keep polarity as-is.
        return

    def current_polarity(self) -> str:
        return self._polarity

    def close(self) -> None:
        return


class Mock2182:
    """Keithley 2182 emulator.

    Returns: sign(offset) + noise + drift (+ occasional outliers).
    Sign is taken from switch polarity.
    """

    def __init__(self, sim: SimConfig, polarity_provider: Callable[[], str]):
        self.sim = sim
        self._polarity_provider = polarity_provider
        self._t0 = time.time()

    def configure(self) -> None:
        return

    def dfil_cycle_before_measurement(self) -> None:
        # mimic OFF/ON filter cycle quickly
        time.sleep(0.01)

    def read_fresh(self) -> float:
        pol = self._polarity_provider()  # "+" or "-"
        sign = 1.0 if pol == "+" else -1.0

        dt_min = (time.time() - self._t0) / 60.0
        drift_uV = self.sim.drift_uV_per_min * dt_min

        v_uV = sign * self.sim.offset_uV + drift_uV
        v_uV += random.gauss(0.0, self.sim.noise_rms_uV)

        if self.sim.outlier_prob > 0 and random.random() < self.sim.outlier_prob:
            v_uV += random.choice([-1.0, 1.0]) * self.sim.outlier_uV

        return v_uV * 1e-6

    def close(self) -> None:
        return


class MockLTE300:
    """LTE-300 emulator."""

    def __init__(self, sim: SimConfig):
        self.sim = sim

    def read_temperature_c(self) -> float:
        return float(self.sim.temp_c + random.gauss(0.0, self.sim.temp_noise_c))

    def close(self) -> None:
        return
