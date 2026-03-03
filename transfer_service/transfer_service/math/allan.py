from typing import List, Tuple
import numpy as np

def allan_deviation(y: List[float], fs_hz: float) -> Tuple[List[float], List[float]]:
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 10:
        return [], []
    taus: List[float] = []
    adevs: List[float] = []
    max_m = n // 10
    for m in range(1, max_m + 1):
        tau = m / fs_hz
        d = y[2*m:] - 2*y[m:-m] + y[:-2*m]
        if len(d) == 0:
            continue
        avar = np.sum(d**2) / (2 * len(d) * (tau**2))
        taus.append(float(tau))
        adevs.append(float(np.sqrt(avar)))
    return taus, adevs
