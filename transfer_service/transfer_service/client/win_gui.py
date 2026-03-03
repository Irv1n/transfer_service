from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import requests

DEFAULT_RPI = "http://192.168.1.50:8000"


def _int_or_none(s: str):
    s = (s or "").strip()
    if not s:
        return None
    return int(s)


def _str_or_none(s: str):
    s = (s or "").strip()
    return s if s else None


class DutRow:
    def __init__(self, parent: ttk.Frame, on_remove):
        self.parent = parent
        self.on_remove = on_remove
        self.id_var = tk.StringVar(value="")
        self.ch_var = tk.StringVar(value="")
        self._build()

    def _build(self):
        self.row = ttk.Frame(self.parent)
        self.row.grid(sticky="w", pady=1)

        ttk.Label(self.row, text="DUT id").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.row, textvariable=self.id_var, width=14).grid(row=0, column=1, padx=(4, 10))
        ttk.Label(self.row, text="ch").grid(row=0, column=2, sticky="w")
        ttk.Entry(self.row, textvariable=self.ch_var, width=5).grid(row=0, column=3, padx=(4, 10))
        ttk.Button(self.row, text="Удалить", command=self.remove).grid(row=0, column=4, padx=(0, 0))

    def remove(self):
        try:
            self.row.destroy()
        finally:
            self.on_remove(self)

    def get_payload(self):
        did = _str_or_none(self.id_var.get())
        ch = _int_or_none(self.ch_var.get())
        if not did or not ch:
            return None
        return {"id": did, "channel": ch}


class LevelUI:
    def __init__(self, parent: ttk.Frame, title: str, default_ref_id: str, default_ref_ch: str, default_ref_val: str, default_ref_u: str):
        self.parent = parent
        self.title = title

        self.ref_id = tk.StringVar(value=default_ref_id)
        self.ref_ch = tk.StringVar(value=default_ref_ch)
        self.ref_val = tk.StringVar(value=default_ref_val)
        self.ref_u = tk.StringVar(value=default_ref_u)

        self.rows: list[DutRow] = []
        self._build()

    def _build(self):
        ttk.Label(self.parent, text=self.title).grid(sticky="w")

        # REF line
        ref = ttk.Frame(self.parent)
        ref.grid(sticky="w", pady=(2, 2))

        ttk.Label(ref, text="REF id").grid(row=0, column=0, sticky="w")
        ttk.Entry(ref, textvariable=self.ref_id, width=14).grid(row=0, column=1, padx=(4, 10))
        ttk.Label(ref, text="REF ch").grid(row=0, column=2, sticky="w")
        ttk.Entry(ref, textvariable=self.ref_ch, width=5).grid(row=0, column=3, padx=(4, 10))
        ttk.Label(ref, text="REF value (V)").grid(row=0, column=4, sticky="w")
        ttk.Entry(ref, textvariable=self.ref_val, width=16).grid(row=0, column=5, padx=(4, 10))
        ttk.Label(ref, text="u(ref) (V)").grid(row=0, column=6, sticky="w")
        ttk.Entry(ref, textvariable=self.ref_u, width=12).grid(row=0, column=7, padx=(4, 0))

        # DUT list header
        dut_box = ttk.LabelFrame(self.parent, text="DUT list")
        dut_box.grid(sticky="w", pady=(2, 2))

        self.dut_list_frame = ttk.Frame(dut_box, padding=4)
        self.dut_list_frame.grid(sticky="w")

        btns = ttk.Frame(dut_box, padding=(4, 0, 4, 4))
        btns.grid(sticky="w")
        ttk.Button(btns, text="+ Добавить DUT", command=self.add_row).grid(row=0, column=0, sticky="w")

        # start with one row
        self.add_row()

    def add_row(self, dut_id: str = "", dut_ch: str = ""):
        row = DutRow(self.dut_list_frame, self._remove_row)
        row.id_var.set(dut_id)
        row.ch_var.set(dut_ch)
        self.rows.append(row)

    def _remove_row(self, row: DutRow):
        if row in self.rows:
            self.rows.remove(row)

    def build_level_payload(self, name: str, cell_type: str, alpha_uv: float | None):
        duts = []
        for r in self.rows:
            p = r.get_payload()
            if p:
                duts.append(p)

        return {
            "name": name,
            "ref": {
                "id": _str_or_none(self.ref_id.get()) or f"REF-{name}",
                "channel": int(self.ref_ch.get()),
                "value_v": float(self.ref_val.get()),
                "u_std_v": float(self.ref_u.get()),
            },
            "duts": duts,
            "cell_type": cell_type,
            "alpha_uV_per_C": alpha_uv,
        }


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Transfer Service (RPi) v0.0.6")
        self.resizable(False, False)

        # Connection
        self.rpi_var = tk.StringVar(value=DEFAULT_RPI)
        self.meter_var = tk.StringVar(value="GPIB0::20::INSTR")
        self.switch_var = tk.StringVar(value="GPIB0::24::INSTR")
        self.lte_port_var = tk.StringVar(value="by-id:FT4QUE2F")

        # Procedure
        self.cycles = tk.StringVar(value="3")
        self.settle = tk.StringVar(value="60")
        self.block = tk.StringVar(value="120")
        self.sample_delay = tk.StringVar(value="0.0")

        # Cell model (common)
        self.cell_type = tk.StringVar(value="saturated")
        self.alpha_uv = tk.StringVar(value="0.0")
        # Simulation
        self.simulation_var = tk.BooleanVar(value=False)
        self.sim_offset_uV = tk.StringVar(value="0.3")
        self.sim_noise_uV = tk.StringVar(value="0.05")
        self.sim_drift_uV_per_min = tk.StringVar(value="0.0")
        self.sim_outlier_prob = tk.StringVar(value="0.0")
        self.sim_outlier_uV = tk.StringVar(value="5.0")
        self.sim_temp_c = tk.StringVar(value="23.0")

        # Job status
        self.job_id = tk.StringVar(value="")
        self.status = tk.StringVar(value="idle")
        self.message = tk.StringVar(value="")
        self.envline = tk.StringVar(value="ENV: ---")

        self._build()
        self._poll_env()

    def _build(self):
        frm = ttk.Frame(self, padding=10)
        frm.grid()

        r = 0
        ttk.Label(frm, text="RPi URL").grid(row=r, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.rpi_var, width=46).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Label(frm, text="2182 VISA").grid(row=r, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.meter_var, width=46).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Label(frm, text="320B VISA").grid(row=r, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.switch_var, width=46).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Label(frm, text="LTE-300 port (path or by-id:SERIAL)").grid(row=r, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.lte_port_var, width=46).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Separator(frm).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1

        # Procedure row
        pf = ttk.Frame(frm); pf.grid(row=r, column=0, columnspan=2, sticky="w")
        ttk.Label(pf, text="cycles").grid(row=0, column=0, sticky="w")
        ttk.Entry(pf, textvariable=self.cycles, width=6).grid(row=0, column=1, padx=(4, 12))
        ttk.Label(pf, text="settle (s)").grid(row=0, column=2, sticky="w")
        ttk.Entry(pf, textvariable=self.settle, width=6).grid(row=0, column=3, padx=(4, 12))
        ttk.Label(pf, text="block (s)").grid(row=0, column=4, sticky="w")
        ttk.Entry(pf, textvariable=self.block, width=6).grid(row=0, column=5, padx=(4, 12))
        ttk.Label(pf, text="sample delay (s)").grid(row=0, column=6, sticky="w")
        ttk.Entry(pf, textvariable=self.sample_delay, width=6).grid(row=0, column=7, padx=(4, 0))
        r += 1

        ttk.Separator(frm).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1

        # Levels side-by-side
        lvl_frame = ttk.Frame(frm)
        lvl_frame.grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1

        l10 = ttk.Frame(lvl_frame)
        l10.grid(row=0, column=0, sticky="nw")
        self.level10 = LevelUI(l10, "10 V (REF + DUT list)", "REF10-01", "3", "10.00000012", "0.3e-6")
        # examples
        self.level10.rows[0].id_var.set("DUT10-05")
        self.level10.rows[0].ch_var.set("5")
        self.level10.add_row("DUT10-09", "9")

        ttk.Separator(lvl_frame, orient="vertical").grid(row=0, column=1, sticky="ns", padx=10)

        l1018 = ttk.Frame(lvl_frame)
        l1018.grid(row=0, column=2, sticky="nw")
        self.level1018 = LevelUI(l1018, "1.018 V (REF + DUT list)", "REF1018-01", "7", "1.018000011", "0.05e-6")
        self.level1018.rows[0].id_var.set("DUT1018-11")
        self.level1018.rows[0].ch_var.set("11")

        ttk.Separator(frm).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1

        # Cell model
        cf = ttk.Frame(frm); cf.grid(row=r, column=0, columnspan=2, sticky="w")
        ttk.Label(cf, text="Cell type").grid(row=0, column=0, sticky="w")
        ttk.Combobox(cf, textvariable=self.cell_type, values=["saturated", "unsaturated"], width=12, state="readonly").grid(row=0, column=1, padx=(4, 12))
        ttk.Label(cf, text="alpha (µV/°C) for unsat").grid(row=0, column=2, sticky="w")
        ttk.Entry(cf, textvariable=self.alpha_uv, width=10).grid(row=0, column=3, padx=(4, 0))
        r += 1
        # Simulation controls
        sf = ttk.LabelFrame(frm, text="Simulation (no instruments)")
        sf.grid(row=r, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Checkbutton(sf, text="Enable simulation", variable=self.simulation_var).grid(row=0, column=0, sticky="w", padx=6, pady=4)

        srow = ttk.Frame(sf)
        srow.grid(row=1, column=0, sticky="w", padx=6, pady=(0, 6))
        ttk.Label(srow, text="offset (µV)").grid(row=0, column=0, sticky="w")
        ttk.Entry(srow, textvariable=self.sim_offset_uV, width=8).grid(row=0, column=1, padx=(4, 12))
        ttk.Label(srow, text="noise RMS (µV)").grid(row=0, column=2, sticky="w")
        ttk.Entry(srow, textvariable=self.sim_noise_uV, width=8).grid(row=0, column=3, padx=(4, 12))
        ttk.Label(srow, text="drift (µV/min)").grid(row=0, column=4, sticky="w")
        ttk.Entry(srow, textvariable=self.sim_drift_uV_per_min, width=8).grid(row=0, column=5, padx=(4, 12))
        ttk.Label(srow, text="outlier p").grid(row=0, column=6, sticky="w")
        ttk.Entry(srow, textvariable=self.sim_outlier_prob, width=6).grid(row=0, column=7, padx=(4, 12))
        ttk.Label(srow, text="outlier (µV)").grid(row=0, column=8, sticky="w")
        ttk.Entry(srow, textvariable=self.sim_outlier_uV, width=8).grid(row=0, column=9, padx=(4, 12))
        ttk.Label(srow, text="temp (°C)").grid(row=0, column=10, sticky="w")
        ttk.Entry(srow, textvariable=self.sim_temp_c, width=6).grid(row=0, column=11, padx=(4, 0))

        r += 1

        ttk.Button(frm, text="Start transfer", command=self.start_job).grid(row=r, column=0, columnspan=2, pady=8)
        r += 1

        self.bar = ttk.Progressbar(frm, length=520, mode="determinate")
        self.bar.grid(row=r, column=0, columnspan=2)
        r += 1

        ttk.Label(frm, text="status").grid(row=r, column=0, sticky="w")
        ttk.Label(frm, textvariable=self.status).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Label(frm, text="message").grid(row=r, column=0, sticky="w")
        ttk.Label(frm, textvariable=self.message).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Label(frm, textvariable=self.envline).grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def start_job(self):
        alpha = float(self.alpha_uv.get()) if self.cell_type.get() == "unsaturated" else None

        levels = [
            self.level10.build_level_payload("10V", self.cell_type.get(), alpha),
            self.level1018.build_level_payload("1.018V", self.cell_type.get(), alpha),
        ]
        levels = [l for l in levels if l["duts"]]

        payload = {
            "meter_resource": self.meter_var.get(),
            "switch_resource": self.switch_var.get(),
            "lte_port": self.lte_port_var.get(),
            "cycles": int(self.cycles.get()),
            "settle_after_switch_s": float(self.settle.get()),
            "block_duration_s": float(self.block.get()),
            "sample_delay_s": float(self.sample_delay.get()),
    "levels": levels,
    "simulation": bool(self.simulation_var.get()),
    "sim_offset_uV": float(self.sim_offset_uV.get()),
    "sim_noise_rms_uV": float(self.sim_noise_uV.get()),
    "sim_drift_uV_per_min": float(self.sim_drift_uV_per_min.get()),
    "sim_outlier_prob": float(self.sim_outlier_prob.get()),
    "sim_outlier_uV": float(self.sim_outlier_uV.get()),
    "sim_temp_c": float(self.sim_temp_c.get()),
}

        try:
            r = requests.post(self.rpi_var.get().rstrip("/") + "/start", json=payload, timeout=20)
            r.raise_for_status()
            self.job_id.set(r.json()["job_id"])
            self.status.set("started")
            self.message.set("Job started")
            self._poll_job()
        except Exception as e:
            messagebox.showerror("Error", repr(e))

    def _poll_job(self):
        jid = self.job_id.get()
        if not jid:
            return
        try:
            r = requests.get(self.rpi_var.get().rstrip("/") + f"/status/{jid}", timeout=5)
            r.raise_for_status()
            j = r.json()
            self.status.set(j.get("status", ""))
            self.message.set(j.get("message", ""))
            self.bar["value"] = float(j.get("progress", 0.0)) * 100.0
            if j.get("status") in ("done", "error"):
                if j.get("status") == "error":
                    messagebox.showerror("Job error", j.get("message", ""))
                return
        except Exception as e:
            self.message.set(f"poll error: {e!r}")
        self.after(1000, self._poll_job)

    def _poll_env(self):
        try:
            r = requests.get(self.rpi_var.get().rstrip("/") + "/env", timeout=2)
            if r.ok:
                e = r.json()
                parts = []
                if e.get("t_c") is not None:
                    parts.append(f"T={e['t_c']:.2f}°C")
                if e.get("rh_pct") is not None:
                    parts.append(f"RH={e['rh_pct']:.1f}%")
                if e.get("p_kpa") is not None:
                    parts.append(f"P={e['p_kpa']:.2f}kPa")
                if e.get("lte_c") is not None:
                    parts.append(f"LTE={e['lte_c']:.2f}°C")
                self.envline.set("ENV: " + (" | ".join(parts) if parts else "---"))
        except Exception:
            pass
        self.after(1000, self._poll_env)


if __name__ == "__main__":
    App().mainloop()
