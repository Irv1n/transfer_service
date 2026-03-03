import csv
from pathlib import Path
from typing import Iterable, Tuple, Optional

Row = Tuple[float, str, float, float, Optional[float], Optional[float], Optional[float]]

def append_raw_csv(path: Path, rows: Iterable[Row]) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["t_epoch", "polarity", "value_V", "lte_temp_C", "env_t_C", "env_rh_pct", "env_p_kpa"])
        w.writerows(rows)
