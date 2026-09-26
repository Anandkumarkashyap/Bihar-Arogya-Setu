import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
HOSPITALS_CSV = "hospitals.csv"
OUTPUT_CSV = "availability_log.csv"

DAYS_OF_HISTORY = 30          # how many days of history to simulate
INTERVAL_MINUTES = 30         # granularity of readings
RANDOM_SEED = 42

# Baseline occupancy fraction (0 = empty, 1 = full) by hospital type.
# Govt hospitals tend to run closer to full capacity than private ones.
BASE_OCCUPANCY = {
    "govt": 0.80,
    "private": 0.55,
}

# How much extra occupancy at "busy" hours (night 8pm-2am) vs normal
NIGHT_OCCUPANCY_BUMP = 0.10
WEEKEND_OCCUPANCY_BUMP = 0.07

# Random noise std-dev added on top of the structured pattern
NOISE_STD = 0.06

# Probability, per hospital per day, of a "shock event" that spikes
# occupancy sharply for a few hours (e.g. mass casualty, festival, outbreak)
SHOCK_EVENT_PROB_PER_DAY = 0.03
SHOCK_EVENT_OCCUPANCY_BUMP = 0.30
SHOCK_EVENT_DURATION_HOURS = 4

# Vaccine slots behave differently — they're consumed during day hours only
# (clinics aren't giving vaccines at 2am) and refill each morning.
VACCINE_ACTIVE_HOURS = range(9, 17)  # 9 AM - 5 PM


def hour_occupancy_multiplier(hour: int) -> float:
    """Returns an additive occupancy bump based on hour of day."""
    if hour >= 20 or hour < 2:
        return NIGHT_OCCUPANCY_BUMP
    return 0.0


def simulate_hospital_series(hospital_row, timestamps, rng):
    """Simulate beds/icu/vaccine availability series for one hospital."""
    h_type = hospital_row["type"]
    base_occ = BASE_OCCUPANCY.get(h_type, 0.6)

    total_beds = hospital_row["total_beds"]
    total_icu = hospital_row["total_icu"]
    total_vax = hospital_row["total_vaccine_slots"]

    records = []

    # Precompute shock-event windows: pick random days this hospital has a shock
    shock_windows = []
    n_days = DAYS_OF_HISTORY
    for d in range(n_days):
        if rng.random() < SHOCK_EVENT_PROB_PER_DAY:
            day_start = timestamps[0] + timedelta(days=d)
            shock_hour = rng.integers(0, 24)
            shock_start = day_start.replace(hour=int(shock_hour), minute=0)
            shock_end = shock_start + timedelta(hours=SHOCK_EVENT_DURATION_HOURS)
            shock_windows.append((shock_start, shock_end))

    for ts in timestamps:
        hour = ts.hour
        is_weekend = ts.weekday() >= 5  # Sat=5, Sun=6

        occ = base_occ
        occ += hour_occupancy_multiplier(hour)
        if is_weekend:
            occ += WEEKEND_OCCUPANCY_BUMP

        # apply shock events
        for (s_start, s_end) in shock_windows:
            if s_start <= ts <= s_end:
                occ += SHOCK_EVENT_OCCUPANCY_BUMP
                break

        # noise
        occ += rng.normal(0, NOISE_STD)
        occ = np.clip(occ, 0.0, 0.99)  # never fully 100% full (a bed frees up)

        beds_available = max(0, int(round(total_beds * (1 - occ))))
        icu_available = max(0, int(round(total_icu * (1 - occ))))

        # Vaccines: only "active" during day hours; at night, slots stay at
        # whatever was left at 5pm (clinic closed, no change) and reset each
        # morning at 9am to full capacity.
        if total_vax > 0:
            if hour in VACCINE_ACTIVE_HOURS:
                vax_occ = np.clip(
                    (hour - 9) / 8 * 0.7 + rng.normal(0, 0.08), 0, 0.95
                )  # slots deplete through the day
                vaccine_available = max(0, int(round(total_vax * (1 - vax_occ))))
            elif hour < 9:
                vaccine_available = total_vax  # not yet opened, full
            else:
                vaccine_available = int(round(total_vax * 0.15))  # closed, minimal leftover shown
        else:
            vaccine_available = 0

        records.append({
            "timestamp": ts,
            "hospital_id": hospital_row["hospital_id"],
            "beds_available": beds_available,
            "icu_available": icu_available,
            "vaccine_slots_available": vaccine_available,
        })

    return records


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    hospitals = pd.read_csv(HOSPITALS_CSV)

    end_time = datetime.now().replace(minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(days=DAYS_OF_HISTORY)
    timestamps = pd.date_range(start=start_time, end=end_time, freq=f"{INTERVAL_MINUTES}min")

    all_records = []
    for _, hospital_row in hospitals.iterrows():
        recs = simulate_hospital_series(hospital_row, timestamps, rng)
        all_records.extend(recs)

    df = pd.DataFrame(all_records)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Generated {len(df):,} rows for {hospitals.shape[0]} hospitals")
    print(f"Time range: {start_time} to {end_time} (every {INTERVAL_MINUTES} min)")
    print(f"Saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
