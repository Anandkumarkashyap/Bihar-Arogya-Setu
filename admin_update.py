"""
admin_update.py

Shared database functions for hospital staff updates. This module is now
imported by app.py (the single unified portal) rather than run standalone,
so it intentionally contains NO top-level Streamlit UI code -- only plain
functions. Keeping it UI-free avoids duplicate page setup / duplicate forms
when imported.

Every update:
  1. Overwrites availability_current for that hospital (the "live" value
     patients see)
  2. Appends a row to availability_history (so nothing is ever lost, and
     this log can later be used to retrain the forecasting model on REAL
     data instead of simulated data)
"""

import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "hospital_portal.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def load_hospitals():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM hospitals ORDER BY name", conn)
    conn.close()
    return df


def load_current(hospital_id):
    conn = get_connection()
    row = pd.read_sql(
        "SELECT * FROM availability_current WHERE hospital_id = ?",
        conn, params=(hospital_id,)
    )
    conn.close()
    return row.iloc[0] if not row.empty else None


def load_history(hospital_id, limit=10):
    conn = get_connection()
    history = pd.read_sql(
        """SELECT updated_at, beds_available, icu_available, vaccine_slots_available, updated_by
           FROM availability_history WHERE hospital_id = ?
           ORDER BY updated_at DESC LIMIT ?""",
        conn, params=(hospital_id, limit)
    )
    conn.close()
    return history


def update_availability(hospital_id, beds, icu, vaccine, updated_by):
    """
    Writes a new availability update. `updated_by` (staff ID) is mandatory --
    this is a hard security requirement, not just a UI nicety, so it is
    validated here too in case this function is ever called from somewhere
    other than the form (e.g. a future API endpoint).
    """
    staff_id_clean = (updated_by or "").strip()
    if len(staff_id_clean) < 4:
        raise ValueError("Staff ID is mandatory and must be at least 4 characters.")

    conn = get_connection()
    now = datetime.now().isoformat(timespec="seconds")

    conn.execute("""
        UPDATE availability_current
        SET beds_available = ?, icu_available = ?, vaccine_slots_available = ?,
            last_updated = ?, updated_by = ?
        WHERE hospital_id = ?
    """, (beds, icu, vaccine, now, staff_id_clean, hospital_id))

    conn.execute("""
        INSERT INTO availability_history
        (hospital_id, beds_available, icu_available, vaccine_slots_available, updated_at, updated_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (hospital_id, beds, icu, vaccine, now, staff_id_clean))

    conn.commit()
    conn.close()
