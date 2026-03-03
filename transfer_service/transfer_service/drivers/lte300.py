from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
import glob
import re
import serial


def resolve_lte_port(port_or_by_id: str) -> str:
    """Resolve LTE-300 serial port.

    Accepts:
      1) Absolute device path, e.g. `/dev/ttyUSB0` or `/dev/serial/by-id/usb-FTDI_...`
      2) By-id selector, e.g. `by-id:FT4QUE2F` (substring match in `/dev/serial/by-id/*`)

    Returns resolved device path to pass into pyserial.
    """
    s = (port_or_by_id or "").strip()
    if not s:
        raise ValueError("LTE-300 port is empty")

    if s.startswith("by-id:"):
        needle = s.split("by-id:", 1)[1].strip()
        if not needle:
            raise ValueError("LTE-300 by-id selector is empty, use e.g. by-id:FT4QUE2F")
        candidates = sorted(glob.glob("/dev/serial/by-id/*"))
        for c in candidates:
            if needle in Path(c).name:
                return c
        raise FileNotFoundError(f"LTE-300 by-id '{needle}' not found in /dev/serial/by-id/")
    return s


@dataclass
class LTE300Config:
    # Can be:
    #   - /dev/ttyUSB0
    #   - /dev/serial/by-id/usb-FTDI_...-if00-port0
    #   - by-id:FT4QUE2F   (substring selector)
    port: str
    baudrate: int = 4800
    timeout_s: float = 1.0
    write_timeout_s: float = 1.0
    warmup_after_open_s: float = 0.2


class LTE300:
    """LTE-300 temperature reader via USB-Serial."""

    def __init__(self, cfg: LTE300Config):
        self.cfg = cfg
        port = resolve_lte_port(cfg.port)

        self.ser = serial.Serial(
            port=port,
            baudrate=cfg.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=cfg.timeout_s,
            write_timeout=cfg.write_timeout_s,
        )
        self.ser.dtr = True
        self.ser.rts = False

        time.sleep(cfg.warmup_after_open_s)
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass

    def read_temperature_c(self) -> float:
        # очищаем буфер перед запросом
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass

        self.ser.write(b"d\r")

        # читаем строку полностью до \n
        resp = self.ser.readline()
        if not resp:
            raise TimeoutError("LTE-300: no response")

        s = resp.decode("ascii", errors="replace").strip()

        # извлекаем все числа из строки
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", s)

        if len(nums) >= 2:
            # второе число — температура
            return float(nums[1])

        raise ValueError(f"LTE-300: bad response: {s!r}")

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass
