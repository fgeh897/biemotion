"""Pure longing calculations with no Sims 4 runtime imports."""


def compute_longing_intensity(elapsed_minutes, start_minutes, full_minutes):
    if elapsed_minutes is None:
        return 0.0
    start = float(start_minutes)
    full = max(start + 1.0, float(full_minutes))
    if float(elapsed_minutes) <= start:
        return 0.0
    return min(
        100.0,
        max(
            0.0,
            (float(elapsed_minutes) - start) * 100.0 / (full - start),
        ),
    )
