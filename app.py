"""
app.py

Streamlit dashboard: "Bihar Hospital Bed & Vaccine Finder"

Run with:
    streamlit run app.py

Lets a user:
  - Enter/select their location (or pick a city to auto-fill coordinates)
  - Choose what they need: bed / icu / vaccine
  - Optionally specify a specialty (pediatric, maternity, cardiac, etc.)
  - Adjust ranking weights (distance vs availability vs specialty)
  - See ranked hospital results on a map + as a table with phone numbers
"""

import streamlit as st
import pandas as pd
import pydeck as pdk

from rank_hospitals import rank_hospitals, load_latest_availability, RESOURCE_COLUMN_MAP
from admin_update import (
    load_hospitals as load_all_hospitals,
    load_current as load_current_availability,
    load_history as load_availability_history,
    update_availability as write_availability_update,
)

st.set_page_config(page_title="Bihar Arogya Setu", layout="wide")

st.title("🏥 Bihar Arogya Setu")
st.caption(
    "A decision-support prototype for emergency hospital referral — "
    "covering Muzaffarpur, Patna, and Darbhanga. "
    "Availability is staff-updated where available, simulated otherwise — not official live hospital data."
)

# ---------------------------------------------------------------------------
# Sidebar: inputs
# ---------------------------------------------------------------------------
st.sidebar.header("Patient / Search Details")

CITY_PRESETS = {
    "Muzaffarpur (Railway Jn.)": (26.1225, 85.3906),
    "Patna (Kankarbagh)": (25.5978, 85.1527),
    "Darbhanga (Laheriasarai)": (26.1328, 85.8973),
    "Custom (enter manually)": None,
}

city_choice = st.sidebar.selectbox("Quick location preset", list(CITY_PRESETS.keys()))

if CITY_PRESETS[city_choice] is not None:
    default_lat, default_lon = CITY_PRESETS[city_choice]
    patient_lat = st.sidebar.number_input("Latitude", value=default_lat, format="%.6f")
    patient_lon = st.sidebar.number_input("Longitude", value=default_lon, format="%.6f")
else:
    custom_address = st.sidebar.text_input("Enter your address/city", placeholder="e.g. Gandhi Maidan, Patna")
    default_lat, default_lon = 26.1225, 85.3906
    if custom_address:
        try:
            from geopy.geocoders import ArcGIS, Nominatim
            
            search_query = custom_address
            if "bihar" not in custom_address.lower():
                search_query = f"{custom_address}, Bihar, India"
                
            arcgis = ArcGIS(timeout=10)
            location = arcgis.geocode(search_query)
            
            if not location:
                location = arcgis.geocode(custom_address)
                
            if not location:
                nom = Nominatim(user_agent="bihar_arogya_setu", timeout=10)
                location = nom.geocode(search_query) or nom.geocode(custom_address)
                
            if location:
                default_lat, default_lon = location.latitude, location.longitude
                st.sidebar.success(f"Found: {location.address.split(',')[0]}")
            else:
                st.sidebar.error("Location not found. Try adding a nearby town or district name.")
        except Exception:
            st.sidebar.error("Map service busy. Try adjusting Latitude/Longitude manually.")
    
    patient_lat = st.sidebar.number_input("Latitude", value=default_lat, format="%.6f")
    patient_lon = st.sidebar.number_input("Longitude", value=default_lon, format="%.6f")

resource = st.sidebar.selectbox(
    "What does the patient need?",
    options=list(RESOURCE_COLUMN_MAP.keys()),
    format_func=lambda x: {"bed": "General Bed", "icu": "ICU Bed", "vaccine": "Vaccine Slot"}[x],
)

SPECIALTIES_LIST = [
    "None (Any)", "admin-coordination", "cancer", "ccu", "child", "dengue", "dental",
    "dialysis", "emergency", "eye", "general", "gynae", "icu", "ivf", "leprosy",
    "liver-transplant", "maternity", "multi-speciality", "neurosciences", "nicu",
    "oncology", "ortho", "orthopaedic", "pediatric", "skin", "superspeciality",
    "surgery", "trauma", "urology"
]
specialty_choice = st.sidebar.selectbox("Specialty needed (optional)", SPECIALTIES_LIST)
specialty = "" if specialty_choice == "None (Any)" else specialty_choice

st.sidebar.subheader("What's most important to you?")
st.sidebar.caption("Rate each factor's importance from 0 (Don't care) to 100 (Very important).")
w_distance_raw = st.sidebar.slider("Distance (Closer to patient)", 0, 100, 45, 5, format="%d%%")
w_availability_raw = st.sidebar.slider("Availability (More open beds/slots)", 0, 100, 25, 5, format="%d%%")
w_specialty_raw = st.sidebar.slider("Specialty Match (Exact department)", 0, 100, 20, 5, format="%d%%")
w_trend_raw = st.sidebar.slider(
    "Future Trend (Will they run out soon?)", 0, 100, 10, 5,
    format="%d%%",
    help="Prefers hospitals predicted to have MORE availability soon over ones 'filling fast'. Only applies to bed search."
)

total_weight = w_distance_raw + w_availability_raw + w_specialty_raw + w_trend_raw
if total_weight == 0:
    w_distance, w_availability, w_specialty, w_trend = 0.25, 0.25, 0.25, 0.25
else:
    w_distance = w_distance_raw / total_weight
    w_availability = w_availability_raw / total_weight
    w_specialty = w_specialty_raw / total_weight
    w_trend = w_trend_raw / total_weight

top_n = st.sidebar.slider("Number of results", 1, 15, 5)

search_clicked = st.sidebar.button("🔍 Find Hospitals", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Hidden staff access -- collapsed by default, no visible hint it unlocks
# an update form. Patients browsing the page will not notice anything odd.
# ---------------------------------------------------------------------------
st.sidebar.divider()
with st.sidebar.expander("⚙️ Staff Access"):
    if "staff_unlocked" not in st.session_state:
        st.session_state["staff_unlocked"] = False
        st.session_state["staff_hospital_id"] = None
        st.session_state["staff_hospital_name"] = None

    if not st.session_state["staff_unlocked"]:
        hospitals_df = load_all_hospitals()
        selected_hospital_name = st.selectbox(
            "Select your hospital", hospitals_df["name"].tolist(), key="login_hospital_select"
        )
        entered_code = st.text_input("Access code", type="password", key="staff_code_input")
        if st.button("Unlock", key="staff_unlock_btn"):
            correct_code = st.secrets.get("staff_access_code", None)
            if correct_code is not None and entered_code == correct_code:
                st.session_state["staff_unlocked"] = True
                st.session_state["staff_hospital_name"] = selected_hospital_name
                row = hospitals_df[hospitals_df["name"] == selected_hospital_name].iloc[0]
                st.session_state["staff_hospital_id"] = int(row["hospital_id"])
                st.rerun()
            else:
                st.error("Incorrect code.")
    else:
        st.success(f"Unlocked for: {st.session_state['staff_hospital_name']}")
        if st.button("Lock again", key="staff_lock_btn"):
            st.session_state["staff_unlocked"] = False
            st.session_state["staff_hospital_id"] = None
            st.session_state["staff_hospital_name"] = None
            st.rerun()

# ---------------------------------------------------------------------------
# STAFF PANEL -- only rendered if this session has unlocked it
# ---------------------------------------------------------------------------
if st.session_state.get("staff_unlocked", False):
    st.header("🔧 Staff Panel — Update Hospital Availability")
    st.caption(
        "This section is only visible after entering the correct staff access code. "
        "Patients never see this panel."
    )

    hospitals_df = load_all_hospitals()
    staff_hospital_id = st.session_state["staff_hospital_id"]
    staff_hospital_name = st.session_state["staff_hospital_name"]
    staff_hospital_row = hospitals_df[hospitals_df["hospital_id"] == staff_hospital_id].iloc[0]
    
    st.subheader(f"Updating: {staff_hospital_name}")

    current = load_current_availability(staff_hospital_id)

    if current is not None:
        st.write(
            f"Current — Beds: **{current['beds_available']}**/{staff_hospital_row['total_beds']} | "
            f"ICU: **{current['icu_available']}**/{staff_hospital_row['total_icu']} | "
            f"Vaccine: **{current['vaccine_slots_available']}**/{staff_hospital_row['total_vaccine_slots']}"
        )
        st.caption(f"Last updated: {current['last_updated']} by {current['updated_by']}")

    with st.form("staff_update_form"):
        new_beds = st.number_input(
            "Beds available", min_value=0, max_value=int(staff_hospital_row["total_beds"]),
            value=int(current["beds_available"]) if current is not None else 0,
        )
        new_icu = st.number_input(
            "ICU beds available", min_value=0, max_value=int(staff_hospital_row["total_icu"]),
            value=int(current["icu_available"]) if current is not None else 0,
        )
        new_vaccine = st.number_input(
            "Vaccine slots available", min_value=0, max_value=int(staff_hospital_row["total_vaccine_slots"]),
            value=int(current["vaccine_slots_available"]) if current is not None else 0,
        )
        updated_by = st.text_input(
            "Staff ID (mandatory)",
            placeholder="e.g. MZP-N023, Ward2-Nurse-Priya",
            help="Required for every update. Recorded in the history log against this exact change.",
        )

        if st.form_submit_button("✅ Update availability", type="primary"):
            staff_id_clean = updated_by.strip()
            if len(staff_id_clean) < 4:
                st.error(
                    "Staff ID is mandatory and must be at least 4 characters. "
                    "This is required so every update is traceable to a specific staff member."
                )
            elif staff_id_clean.lower() in {"staff", "nurse", "admin", "test", "na", "n/a", "none"}:
                st.error("Please enter your actual staff ID/name, not a placeholder value.")
            else:
                write_availability_update(staff_hospital_id, new_beds, new_icu, new_vaccine, staff_id_clean)
                st.success(f"Updated {staff_hospital_name} by **{staff_id_clean}**. Patients will see this immediately.")
                st.session_state.pop("last_results", None)  # force a fresh search next time
                st.rerun()

    with st.expander("📜 Recent update history for this hospital"):
        history = load_availability_history(staff_hospital_id)
        if history.empty:
            st.write("No updates logged yet.")
        else:
            st.dataframe(history, use_container_width=True, hide_index=True)

    st.divider()

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------
if search_clicked or "last_results" in st.session_state:
    if search_clicked:
        results = rank_hospitals(
            patient_lat=patient_lat,
            patient_lon=patient_lon,
            resource=resource,
            needed_specialty=specialty if specialty.strip() else None,
            weights={
                "distance": w_distance,
                "availability": w_availability,
                "specialty": w_specialty,
                "trend": w_trend,
            },
            top_n=top_n,
        )
        st.session_state["last_results"] = results
    else:
        results = st.session_state["last_results"]

    if results.empty:
        st.warning(
            "No hospitals currently have availability for this resource. "
            "Try a different resource type or widen your search."
        )
    else:
        col1, col2 = st.columns([3, 2])

        with col1:
            st.subheader("📍 Map of Recommended Hospitals")

            hospitals_full = pd.read_csv("hospitals.csv")
            map_df = results.merge(
                hospitals_full[["name", "lat", "lon"]], on="name", how="left"
            )
            map_df["label"] = map_df["name"] + " (" + map_df["available"].astype(str) + " available)"

            patient_point = pd.DataFrame(
                [{"lat": patient_lat, "lon": patient_lon, "label": "📍 Patient location"}]
            )

            top_hospital = map_df.iloc[0]
            
            import requests
            route_coords = [[patient_lon, patient_lat], [top_hospital["lon"], top_hospital["lat"]]]
            route_steps = []
            try:
                osrm_url = f"http://router.project-osrm.org/route/v1/driving/{patient_lon},{patient_lat};{top_hospital['lon']},{top_hospital['lat']}?overview=full&geometries=geojson&steps=true"
                response = requests.get(osrm_url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "Ok":
                        route_coords = data["routes"][0]["geometry"]["coordinates"]
                        route_steps = data["routes"][0]["legs"][0].get("steps", [])
            except Exception:
                pass

            line_df = pd.DataFrame([{
                "path": route_coords,
                "name": top_hospital["name"]
            }])

            layer_hospitals = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position="[lon, lat]",
                get_color="[200, 30, 30, 180]",
                get_radius=400,
                pickable=True,
            )
            layer_patient = pdk.Layer(
                "ScatterplotLayer",
                data=patient_point,
                get_position="[lon, lat]",
                get_color="[30, 100, 220, 220]",
                get_radius=500,
                pickable=True,
            )
            layer_line = pdk.Layer(
                "PathLayer",
                data=line_df,
                get_path="path",
                get_color="[0, 255, 0, 200]",
                width_scale=20,
                width_min_pixels=5,
                get_width=5,
            )

            view_state = pdk.ViewState(
                latitude=patient_lat, longitude=patient_lon, zoom=10, pitch=0
            )

            st.pydeck_chart(
                pdk.Deck(
                    layers=[layer_line, layer_hospitals, layer_patient],
                    initial_view_state=view_state,
                    tooltip={"text": "{label}"},
                )
            )

        with col2:
            st.subheader("📋 Ranked Results")
            display_df = results.copy()
            display_df["distance_km"] = display_df["distance_km"].round(2)
            display_df["score"] = display_df["score"].round(3)
            st.dataframe(
                display_df[["name", "type", "distance_km", "available", "total", "trend", "score", "phone"]],
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("🏆 Top Recommendation")
        top = results.iloc[0]
        trend_suffix = f" — Trend: {top['trend']}" if top['trend'] != "N/A" else ""
        st.success(
            f"**{top['name']}** ({top['type'].title()}) — "
            f"{top['distance_km']:.1f} km away, "
            f"{int(top['available'])}/{int(top['total'])} {resource} slots available."
            f"{trend_suffix} "
            f"Phone: {top['phone'] if pd.notna(top['phone']) else 'Not listed'}"
        )
        
        if 'route_steps' in locals() and route_steps:
            with st.expander("🚗 Turn-by-Turn Navigation Instructions"):
                for i, step in enumerate(route_steps):
                    maneuver = step.get("maneuver", {})
                    instruction = maneuver.get("type", "").replace("-", " ")
                    if "modifier" in maneuver:
                        instruction += " " + maneuver["modifier"].replace("-", " ")
                    name = step.get("name", "")
                    if name:
                        instruction += f" onto **{name}**"
                    distance = step.get("distance", 0)
                    if instruction:
                        st.markdown(f"{i+1}. {instruction.capitalize()} (drive {distance:.0f}m)")
else:
    st.info("Set the patient's location and needs in the sidebar, then click **Find Hospitals**.")

# ---------------------------------------------------------------------------
# Footer: dataset snapshot
# ---------------------------------------------------------------------------
with st.expander("ℹ️ About this dataset"):
    st.markdown(
        """
        - **Hospitals**: 30 real hospitals across Muzaffarpur, Patna, and Darbhanga
          (names, coordinates from public listings).
        - **Capacity figures** (total beds/ICU/vaccine slots): estimated, not
          officially verified — placeholder values for demo purposes.
        - **Availability data**: fully simulated with realistic day/night,
          weekday/weekend, and random "shock event" patterns — not live data.
        - This is a fresher/portfolio project inspired by real government
          announcements about hospital bed-availability portals, not an
          official government tool.
        """
    )
