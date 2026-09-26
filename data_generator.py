import pandas as pd
import numpy as np
import random
import os

# Central Patna Coordinates
PATNA_LAT = 25.5941
PATNA_LON = 85.1376

def generate_hospitals(num_hospitals=20):
    np.random.seed(42)
    random.seed(42)
    
    names = [f"Hospital {i+1}" for i in range(num_hospitals)]
    # Add a bit of noise to coordinates for spread around Patna
    lats = PATNA_LAT + np.random.uniform(-0.05, 0.05, num_hospitals)
    lons = PATNA_LON + np.random.uniform(-0.05, 0.05, num_hospitals)
    
    total_general_beds = np.random.randint(50, 200, num_hospitals)
    total_icu_beds = np.random.randint(10, 50, num_hospitals)
    
    df = pd.DataFrame({
        'hospital_id': range(1, num_hospitals + 1),
        'name': names,
        'lat': lats,
        'lon': lons,
        'total_general_beds': total_general_beds,
        'total_icu_beds': total_icu_beds
    })
    return df

def generate_time_series_data(hospitals_df, days=7):
    # Generates historical capacity data
    np.random.seed(42)
    records = []
    
    start_time = pd.Timestamp.now().floor('H') - pd.Timedelta(days=days)
    times = pd.date_range(start=start_time, end=pd.Timestamp.now().floor('H'), freq='1H')
    
    for _, row in hospitals_df.iterrows():
        hid = row['hospital_id']
        t_gen = row['total_general_beds']
        t_icu = row['total_icu_beds']
        
        # Start with some random availability
        curr_gen = int(t_gen * np.random.uniform(0.2, 0.8))
        curr_icu = int(t_icu * np.random.uniform(0.1, 0.6))
        
        for t in times:
            # Random walk
            gen_change = np.random.randint(-5, 6)
            icu_change = np.random.randint(-2, 3)
            
            # Evening/Night tends to have slightly more occupancy (less availability)
            if 18 <= t.hour <= 23 or 0 <= t.hour <= 6:
                gen_change -= 1
                icu_change -= 1
                
            curr_gen = max(0, min(t_gen, curr_gen + gen_change))
            curr_icu = max(0, min(t_icu, curr_icu + icu_change))
            
            records.append({
                'hospital_id': hid,
                'timestamp': t,
                'avail_general_beds': curr_gen,
                'avail_icu_beds': curr_icu
            })
            
    return pd.DataFrame(records)

if __name__ == "__main__":
    print("Generating simulated data...")
    hospitals = generate_hospitals()
    timeseries = generate_time_series_data(hospitals)
    
    hospitals.to_csv('hospitals.csv', index=False)
    timeseries.to_csv('bed_availability.csv', index=False)
    print("Data generated and saved to hospitals.csv and bed_availability.csv")
