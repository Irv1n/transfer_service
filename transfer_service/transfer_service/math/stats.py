import statistics
from typing import Sequence, Tuple

def mean(x: Sequence[float]) -> float:
    return statistics.fmean(x)

def type_a_u_mean(x: Sequence[float]) -> Tuple[float, float]:
    if len(x) < 2:
        return float("nan"), float("nan")
    s = statistics.stdev(x)
    u = s / (len(x) ** 0.5)
    return s, u
