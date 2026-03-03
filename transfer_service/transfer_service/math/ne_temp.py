def saturated_to_20c(E_t: float, t_c: float) -> float:
    a = 40.6e-6
    b = 0.95e-6
    c = 0.01e-6
    dt = 20.0 - t_c
    return E_t - a*dt - b*(dt**2) + c*(dt**3)

def unsaturated_to_20c_uv_per_c(E_t: float, t_c: float, alpha_uV_per_C: float) -> float:
    alpha_v_per_c = alpha_uV_per_C * 1e-6
    return E_t - alpha_v_per_c * (t_c - 20.0)
