from dataclasses import dataclass
from typing import Sequence
import math
from .stats import type_a_u_mean

@dataclass
class UncResult:
    u_type_a: float
    u_ref: float
    u_combined: float
    U_k2: float

def estimate_uncertainty(delta_samples: Sequence[float], u_ref: float) -> UncResult:
    _, uA = type_a_u_mean(list(delta_samples))
    u_c = math.sqrt((uA ** 2) + (u_ref ** 2))
    return UncResult(u_type_a=uA, u_ref=u_ref, u_combined=u_c, U_k2=2 * u_c)
