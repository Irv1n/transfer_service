def calc_delta(r_plus_mean: float, r_minus_mean: float) -> float:
    return (r_plus_mean - r_minus_mean) / 2.0

def calc_u_dut(u_ref: float, delta: float) -> float:
    return u_ref + delta
