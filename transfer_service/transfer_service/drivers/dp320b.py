from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import pyvisa


@dataclass
class DP320BConfig:
    actuation_delay_s: float = 0.2
    timeout_ms: int = 5000


class Dataproof320B:
    """Dataproof 320B relay scanner."""

    def __init__(self, resource: str, cfg: Optional[DP320BConfig] = None):
        self.cfg = cfg or DP320BConfig()
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(resource)
        self.inst.timeout = self.cfg.timeout_ms
        self.inst.write_termination = "\n"
        self.inst.read_termination = "\n"

    def _w(self, cmd: str) -> None:
        self.inst.write(cmd)
        time.sleep(self.cfg.actuation_delay_s)

    def clear(self) -> None:
        self._w("A00")
        self._w("B00")

    # Дубликат clear?
    def open_all(self) -> None:
        self.clear()

    def close_a(self, ch: int) -> None:
        self._w(f"A{ch:02d}")

    def close_b(self, ch: int) -> None:
        self._w(f"B{ch:02d}")

    def set_pair(self, a_ch: int, b_ch: int) -> None:
        self.clear()
        self.close_a(a_ch)
        self.close_b(b_ch)

    def close(self) -> None:
        try:
            self.inst.close()
        finally:
            try:
                self.rm.close()
            except Exception:
                pass
