"""
rank_hospitals.py

Given a patient's location, the type of emergency, and which resource they
need (bed / icu / vaccine), this module returns a ranked list of hospitals
using the most RECENT availability reading for each hospital.

Scoring formula:
    score = w_dist * (1 / distance_km)
          + w_avail * (available / total)
          + w_spec  * specialty_match (0 or 1)

Higher score = better recommendation. Distance dominates by default since
this is built for EMERGENCY referral, but weights are adjustable.
"""

import pandas as pd
import numpy as np
from math import radians, sin, cos, sqrt, atan2

HOSPITALS_CSV = "hospitals.csv"
AVAILABILITY_CSV = "availability_log.csv"
FORECAST_CSV = "forecast_output.csv"
DB_PATH = "hospital_portal.db"

# Default weights -- tuned for "emergency" use case: distance matters most,
# then how much room they actually have, then specialty fit, then trend.
DEFAULT_WEIGHTS = {
    "distance": 0.45,
    "availability": 0.25,
    "specialty": 0.2,
    "trend": 0.1,
}

# Trend label -> numeric score contribution (0-1 scale, matches other sub-scores)
TREND_SCORE_MAP = {
    "🟢 FREEING UP": 1.0,
    "STABLE": 0.6,
    "⚠️ FILLING FAST": 0.0,
}


def load_forecast(forecast_path=FORECAST_CSV):
    """Returns forecast_output.csv indexed by hospital_id, or None if the
    forecast hasn't been generated yet (keeps ranking usable without it)."""
    try:
        df = pd.read_csv(forecast_path)
        return df.set_index("hospital_id")
    except FileNotFoundError:
        return None

RESOURCE_COLUMN_MAP = {
    "bed": ("beds_available", "total_beds"),
    "icu": ("icu_available", "total_icu"),
    "vaccine": ("vaccine_slots_available", "total_vaccine_slots"),
}


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in km."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def load_latest_availability(availability_path=AVAILABILITY_CSV):
    """Returns a DataFrame with just the most recent reading per hospital.
    Kept for backward compatibility / offline testing with the simulated CSV."""
    df = pd.read_csv(availability_path, parse_dates=["timestamp"])
    latest = df.sort_values("timestamp").groupby("hospital_id").tail(1)
    return latest.set_index("hospital_id")


def load_live_availability(db_path=DB_PATH):
    """
    Returns the LIVE availability_current table from the SQLite database
    (updated by hospital staff via admin_update.py), indexed by hospital_id.
    Returns None if the database doesn't exist yet, so callers can fall
    back to the simulated CSV.
    """
    import sqlite3
    import os
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql("SELECT * FROM availability_current", conn)
        conn.close()
        if df.empty:
            return None
        return df.set_index("hospital_id")
    except Exception:
        return None


def specialty_match_score(hospital_specialties: str, needed_specialty: str) -> float:
    """1.0 if the needed specialty keyword appears in the hospital's
    specialty list, else 0.0. Case-insensitive, simple substring match --
    good enough for a fresher project; could upgrade to fuzzy match later."""
    if not needed_specialty:
        return 0.0
    if pd.isna(hospital_specialties):
        return 0.0
    return 1.0 if needed_specialty.lower() in hospital_specialties.lower() else 0.0


def rank_hospitals(
    patient_lat: float,
    patient_lon: float,
    resource: str = "bed",
    needed_specialty: str = None,
    weights: dict = None,
    top_n: int = 5,
    hospitals_path: str = HOSPITALS_CSV,
    availability_path: str = AVAILABILITY_CSV,
    forecast_path: str = FORECAST_CSV,
    db_path: str = DB_PATH,
    use_forecast: bool = True,
    use_live_db: bool = True,
):
    """
    Main entry point.

    Parameters
    ----------
    patient_lat, patient_lon : float
        Patient's current coordinates.
    resource : str
        One of "bed", "icu", "vaccine" -- which capacity type is needed.
    needed_specialty : str, optional
        e.g. "pediatric", "cardiac", "maternity" -- matched against the
        hospital's specialties column.
    weights : dict, optional
        Override DEFAULT_WEIGHTS, e.g. {"distance": 0.7, "availability": 0.2, "specialty": 0.1}
    top_n : int
        How many ranked results to return.

    Returns
    -------
    pandas.DataFrame sorted by score, descending, with columns:
        name, type, distance_km, available, total, specialty_match, score, phone
    """
    if resource not in RESOURCE_COLUMN_MAP:
        raise ValueError(f"resource must be one of {list(RESOURCE_COLUMN_MAP)}")

    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    avail_col, total_col = RESOURCE_COLUMN_MAP[resource]

    hospitals = pd.read_csv(hospitals_path).set_index("hospital_id")

    # Prefer LIVE data from the database (staff-updated) over the frozen
    # simulated CSV. Falls back automatically if the DB isn't set up yet.
    latest_avail = None
    data_source = "simulated CSV"
    if use_live_db:
        latest_avail = load_live_availability(db_path)
        if latest_avail is not None:
            data_source = "live database"
    if latest_avail is None:
        latest_avail = load_latest_availability(availability_path)

    merged = hospitals.join(latest_avail, how="left")

    # Filter: only hospitals that currently have at least 1 unit available
    merged = merged[merged[avail_col] > 0].copy()

    if merged.empty:
        return pd.DataFrame(columns=[
            "name", "type", "distance_km", "available", "total",
            "specialty_match", "trend", "score", "phone"
        ])

    # Distance
    merged["distance_km"] = merged.apply(
        lambda r: haversine_km(patient_lat, patient_lon, r["lat"], r["lon"]), axis=1
    )

    # Non-linear distance score: strictly prioritizes proximity regardless of dataset scale.
    # 0km = 1.0, 10km = 0.5, 40km = 0.2. Prevents distant hospitals with high availability from taking over.
    merged["distance_score"] = 1.0 / (1.0 + (merged["distance_km"] / 10.0))
    merged["availability_score"] = merged[avail_col] / merged[total_col].replace(0, np.nan)
    merged["availability_score"] = merged["availability_score"].fillna(0)
    merged["specialty_match"] = merged["specialties"].apply(
        lambda s: specialty_match_score(s, needed_specialty)
    )

    # Trend (forecast) sub-score -- optional, only used for the "bed" resource
    # since forecast_availability.py currently trains on beds_available only.
    forecast_df = load_forecast(forecast_path) if use_forecast else None
    if forecast_df is not None and resource == "bed":
        merged = merged.join(forecast_df[["trend", "pred_30min"]], how="left")
        merged["trend"] = merged["trend"].fillna("STABLE")
        merged["trend_score"] = merged["trend"].map(TREND_SCORE_MAP).fillna(0.6)
    else:
        merged["trend"] = "N/A"
        merged["trend_score"] = 0.6  # neutral if no forecast available

    merged["score"] = (
        w["distance"] * merged["distance_score"]
        + w["availability"] * merged["availability_score"]
        + w["specialty"] * merged["specialty_match"]
        + w.get("trend", 0) * merged["trend_score"]
    )

    result = merged.sort_values("score", ascending=False).head(top_n)

    cols = [
        "name", "type", "distance_km", avail_col, total_col,
        "specialty_match", "trend", "score", "phone"
    ]
    final = result[cols].rename(columns={avail_col: "available", total_col: "total"})
    final.attrs["data_source"] = data_source
    return final


if __name__ == "__main__":
    # Example: emergency patient somewhere in central Muzaffarpur needing
    # a general/pediatric bed
    patient_lat, patient_lon = 26.1225, 85.3906  # near Muzaffarpur Jn station

    results = rank_hospitals(
        patient_lat=patient_lat,
        patient_lon=patient_lon,
        resource="bed",
        needed_specialty="pediatric",
        top_n=5,
    )

    print("Top hospital recommendations:\n")
    print(results.to_string(index=False))
