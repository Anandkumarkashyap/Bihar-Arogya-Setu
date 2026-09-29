"""
init_db.py

Creates a SQLite database (hospital_portal.db) with two tables:

  1. hospitals            -- static info (name, location, capacity) --
                              loaded once from hospitals.csv
  2. availability_current -- the LIVE, editable numbers (one row per
                              hospital, always holding its latest values)
  3. availability_history -- every update ever made, kept as a log
                              (useful later for retraining the forecast model
                              on real data instead of simulated data)

Run this once to set up the database:
    python init_db.py

Safe to re-run: it will not duplicate hospitals if they already exist.
"""

import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "hospital_portal.db"
HOSPITALS_CSV = "hospitals.csv"
AVAILABILITY_CSV = "availability_log.csv"  # used only to seed initial current values


def create_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            hospital_id INTEGER PRIMARY KEY,
            name TEXT,
            lat REAL,
            lon REAL,
            type TEXT,
            phone TEXT,
            specialties TEXT,
            total_beds INTEGER,
            total_icu INTEGER,
            total_vaccine_slots INTEGER,
            city TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS availability_current (
            hospital_id INTEGER PRIMARY KEY,
            beds_available INTEGER,
            icu_available INTEGER,
            vaccine_slots_available INTEGER,
            last_updated TEXT,
            updated_by TEXT,
            FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS availability_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id INTEGER,
            beds_available INTEGER,
            icu_available INTEGER,
            vaccine_slots_available INTEGER,
            updated_at TEXT,
            updated_by TEXT,
            FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id)
        )
    """)
    conn.commit()


def seed_hospitals(conn):
    """Load hospitals.csv into the hospitals table if not already populated."""
    existing_count = conn.execute("SELECT COUNT(*) FROM hospitals").fetchone()[0]
    if existing_count > 0:
        print(f"hospitals table already has {existing_count} rows -- skipping seed.")
        return

    df = pd.read_csv(HOSPITALS_CSV)
    df.to_sql("hospitals", conn, if_exists="append", index=False)
    print(f"Seeded {len(df)} hospitals into the database.")


def seed_current_availability(conn):
    """
    Initialize availability_current using the LATEST row per hospital from
    the old simulated availability_log.csv, so the live system starts from
    a realistic baseline instead of zeros.
    """
    existing_count = conn.execute("SELECT COUNT(*) FROM availability_current").fetchone()[0]
    if existing_count > 0:
        print(f"availability_current already has {existing_count} rows -- skipping seed.")
        return

    try:
        sim_df = pd.read_csv(AVAILABILITY_CSV, parse_dates=["timestamp"])
        latest = sim_df.sort_values("timestamp").groupby("hospital_id").tail(1)
        latest = latest.set_index("hospital_id")
    except FileNotFoundError:
        latest = pd.DataFrame()

    hospitals_df = pd.read_csv(HOSPITALS_CSV).set_index("hospital_id")
    
    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    
    for hosp_id, row in hospitals_df.iterrows():
        if hosp_id in latest.index:
            r = latest.loc[hosp_id]
            beds = int(r["beds_available"])
            icu = int(r["icu_available"])
            vacc = int(r["vaccine_slots_available"])
        else:
            beds = int(row["total_beds"])
            icu = int(row["total_icu"])
            vacc = int(row["total_vaccine_slots"])
            
        rows.append((
            int(hosp_id),
            beds,
            icu,
            vacc,
            now,
            "system_seed",
        ))

    conn.executemany("""
        INSERT INTO availability_current
        (hospital_id, beds_available, icu_available, vaccine_slots_available, last_updated, updated_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    print(f"Seeded current availability for {len(rows)} hospitals (baseline = last simulated reading).")


def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    seed_hospitals(conn)
    seed_current_availability(conn)
    conn.close()
    print(f"\nDatabase ready at {DB_PATH}")


if __name__ == "__main__":
    main()
