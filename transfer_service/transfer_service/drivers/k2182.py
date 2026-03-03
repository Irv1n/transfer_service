from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import pyvisa


@dataclass
class K2182Config:
    range_v: float = 0.01
    nplc: float = 10.0
    dfil_count: int = 10
    dfil_window: float = 0.1
    dfil_toggle_wait_s: float = 5.0
    timeout_ms: int = 20000


class Keithley2182:
    """Keithley 2182/2182A driver (minimal) for transfer service."""

    def __init__(self, resource: str, cfg: Optional[K2182Config] = None):
        self.cfg = cfg or K2182Config()
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(resource)
        self.inst.timeout = self.cfg.timeout_ms
        self.inst.write_termination = "\n"
        self.inst.read_termination = "\n"

    def write(self, cmd: str) -> None:
        self.inst.write(cmd)

    def query(self, cmd: str) -> str:
        return self.inst.query(cmd)

    def configure(self) -> None:
        c = self.cfg
        self.write(":SYSTEM:PRESET")
        self.write(f":SENS:VOLT:DC:RANGE {c.range_v}")
        self.write(":SENS:FUNC 'VOLT:DC'")
        self.write(f":SENS:VOLT:DC:NPLC {c.nplc}")
        self.write(f":SENS:VOLT:DFIL:COUN {c.dfil_count}")
        self.write(f":SENS:VOLT:DFIL:WIND {c.dfil_window}")
        self.write(":SENS:VOLT:DFIL:STATE ON")

    def dfil_cycle_before_measurement(self) -> None:
        self.write(":SENS:VOLT:DFIL:STATE OFF")
        time.sleep(self.cfg.dfil_toggle_wait_s)
        self.write(":SENS:VOLT:DFIL:STATE ON")

    def read_fresh(self) -> float:
        return float(self.query(":SENS:DATA:FRESH?").strip())

    def close(self) -> None:
        try:
            self.inst.close()
        finally:
            try:
                self.rm.close()
            except Exception:
                pass
