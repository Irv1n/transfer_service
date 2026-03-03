from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional

try:
    from bme280pi import Sensor  # type: ignore
except Exception:  # pragma: no cover
    Sensor = None  # type: ignore

@dataclass
class BME280Config:
    address: int = 0x76

class BME280Env:
    def __init__(self, cfg: Optional[BME280Config] = None):
        if Sensor is None:
            raise ImportError("bme280pi not installed. Install on RPi: pip install bme280pi")
        self.cfg = cfg or BME280Config()
        self.sensor = Sensor(address=self.cfg.address)

    def read(self) -> Dict[str, Any]:
        d = self.sensor.get_data()
        return {
            "t_c": float(d["temperature"]),
            "rh_pct": float(d["humidity"]),
            "p_kpa": float(d["pressure"]) / 10.0,
        }
