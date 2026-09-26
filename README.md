# 🏥 Bihar Arogya Setu

**A real-time hospital bed & vaccine availability finder for Bihar** — helping patients and families quickly locate available beds, ICU slots, or vaccine appointments during emergencies.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-App-red?logo=streamlit)
![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey?logo=sqlite)
![Status](https://img.shields.io/badge/Status-Prototype-orange)
![License](https://img.shields.io/badge/License-MIT-green)

> ⚠️ **Independent academic/portfolio project — not affiliated with any government body.** Hospital names and locations are real; capacity figures and availability data are estimated/simulated unless updated live via the staff portal.

---

## 📋 Table of Contents
- [Problem](#-problem)
- [What This Project Does](#-what-this-project-does)
- [Tech Stack](#-tech-stack)
- [How It Works](#-how-it-works)
- [Setup & Installation](#-setup--installation)
- [Project Structure](#-project-structure)
- [Screenshots](#-screenshots)
- [Limitations & Future Work](#-limitations--future-work)
- [License](#-license)

---

## 🩺 Problem

During medical emergencies, patients and families often don't know which nearby hospital has an available bed, ICU slot, or vaccine appointment — leading to delays, wasted trips, and overcrowding at some hospitals while others have unused capacity. Several Indian state health departments have discussed building centralized bed-availability portals, but no live public system currently exists for Bihar.

## 💡 What This Project Does

- **Finds the best hospital** for a patient based on distance, current availability, specialty match, and predicted availability trend
- **Covers 30 real hospitals** across Muzaffarpur, Patna, and Darbhanga
- **Lets hospital staff update availability live** through a secure, city-restricted staff portal — no random person can edit hospital data
- **Forecasts availability 30–60 minutes ahead** using a machine learning model trained on historical patterns
- **Visualizes results on an interactive map** with ranked recommendations

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Frontend / Dashboard | Streamlit |
| Database | SQLite |
| ML Forecasting | scikit-learn (Random Forest) |
| Data Processing | pandas, NumPy |
| Mapping | PyDeck |
| Geolocation | Haversine distance formula |

## ⚙️ How It Works

<details>
<summary><b>1. Hospital & availability data</b></summary>

`hospitals.csv` contains 30 real hospitals (name, coordinates, type, specialties, capacity) across three cities. Live availability is stored in a SQLite database (`hospital_portal.db`) and updated by hospital staff in real time.
</details>

<details>
<summary><b>2. Ranking algorithm</b></summary>

Each hospital is scored using a weighted formula:
score = w1 × (1 / distance) + w2 × (available / total) + w3 × specialty_match + w4 × forecast_trend

Weights are adjustable in the UI depending on whether distance or availability should matter more for a given emergency.
</details>

<details>
<summary><b>3. ML forecasting</b></summary>

A separate Random Forest model is trained per hospital using lag features (recent readings) and calendar features (hour, day of week) to predict bed availability 30–60 minutes ahead, flagging hospitals as `FILLING FAST`, `STABLE`, or `FREEING UP`.
</details>

<details>
<summary><b>4. Secure staff updates</b></summary>

Hospital staff unlock a hidden update panel using a **city-specific access code** (so a leaked code only exposes one city). A valid **staff ID (minimum 4 characters, no placeholders)** is mandatory for every update — enforced at both the UI and database level — so every change is traceable.
</details>

## 🚀 Setup & Installation

```bash
# Clone the repo
git clone https://github.com/Anandkumarkashyap/Bihar-Arogya-Setu.git
cd Bihar-Arogya-Setu

# Install dependencies
pip install -r requirements.txt

# Initialize the database (run once)
python init_db.py

# (Optional) Generate simulated historical data + train forecast model
python simulate_availability.py
python forecast_availability.py

# Run the app
streamlit run app.py
```

Before running, set your own staff access codes in `.streamlit/secrets.toml`:
```toml
[staff_access_codes]
Muzaffarpur = "your-code-here"
Patna = "your-code-here"
Darbhanga = "your-code-here"
```

## 📁 Project Structure

├── app.py # Main Streamlit app (patient + staff views)
├── admin_update.py # Database functions for staff updates
├── rank_hospitals.py # Ranking/scoring logic
├── forecast_availability.py # ML forecasting model
├── simulate_availability.py # Generates realistic simulated historical data
├── init_db.py # Sets up the SQLite database
├── hospitals.csv # Static hospital data (30 hospitals)
├── .streamlit/secrets.toml # Staff access codes (not committed to git)
└── README.md


## 📸 Screenshots

*(Add screenshots of the map view, ranked results, and staff panel here)*

## 🔮 Limitations & Future Work

- Staff authentication uses shared city-level codes, not individual logins — a real deployment would need per-hospital credentials
- Capacity figures (total beds/ICU/vaccine slots) are estimated, not officially verified
- Historical availability is simulated; the forecasting model would need retraining on real data once the staff-update history grows
- Currently covers 3 cities — designed to scale to more districts by extending `hospitals.csv`

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

*Built as a data science portfolio project demonstrating end-to-end pipeline design: data collection, live database integration, ML forecasting, and a secure, role-based web application.*
