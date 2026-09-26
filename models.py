import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from geopy.distance import geodesic

def forecast_availability(df_timeseries, hospital_id, bed_type='general', hours_ahead=3):
    """
    Simple Linear Regression to predict bed availability a few hours ahead.
    """
    col = 'beds_available' if bed_type == 'general' else 'icu_available'
    df_h = df_timeseries[df_timeseries['hospital_id'] == hospital_id].copy()
    if df_h.empty:
        return 0
        
    df_h = df_h.sort_values('timestamp')
    # Use last 24 hours for short-term prediction
    df_h = df_h.tail(24)
    
    if len(df_h) < 2:
        return df_h.iloc[-1][col]
        
    # Features: Hours from start
    df_h['hours_from_start'] = (df_h['timestamp'] - df_h['timestamp'].min()).dt.total_seconds() / 3600
    
    X = df_h[['hours_from_start']]
    y = df_h[col]
    
    model = LinearRegression()
    model.fit(X, y)
    
    # Predict
    future_hour = df_h['hours_from_start'].max() + hours_ahead
    pred = model.predict(np.array([[future_hour]]))
    
    # Bound the prediction between 0 and whatever
    return max(0, int(pred[0]))

def rank_hospitals(patient_lat, patient_lon, hospitals_df, timeseries_df, bed_type='general', need_beds=1):
    """
    Rank hospitals based on:
    - Current Availability (Must be >= need_beds)
    - Distance (closer is better)
    - Predicted Availability (higher is better, adds safety margin)
    """
    ranked_list = []
    col = 'beds_available' if bed_type == 'general' else 'icu_available'
    
    # Get latest data per hospital
    latest_time = timeseries_df['timestamp'].max()
    df_latest = timeseries_df[timeseries_df['timestamp'] == latest_time]
    
    for _, hosp in hospitals_df.iterrows():
        hid = hosp['hospital_id']
        h_lat = hosp['lat']
        h_lon = hosp['lon']
        
        # Calculate distance
        dist_km = geodesic((patient_lat, patient_lon), (h_lat, h_lon)).kilometers
        
        # Get current availability
        curr_avail_series = df_latest[df_latest['hospital_id'] == hid][col]
        curr_avail = curr_avail_series.values[0] if not curr_avail_series.empty else 0
        
        if curr_avail < need_beds:
            continue # Skip if not enough beds currently
            
        # Get predicted availability (3 hours ahead)
        pred_avail = forecast_availability(timeseries_df, hid, bed_type, hours_ahead=3)
        
        # Simple scoring formula: 
        # Lower score is better.
        # Score = Distance (km) - (Current_Avail * 0.1) - (Pred_Avail * 0.05)
        # This penalizes long distances, and gives slight preference to hospitals with lots of current and future buffer.
        score = dist_km - (curr_avail * 0.1) - (pred_avail * 0.05)
        
        ranked_list.append({
            'hospital_id': hid,
            'name': hosp['name'],
            'distance_km': round(dist_km, 2),
            'current_avail': curr_avail,
            'predicted_avail_3h': pred_avail,
            'score': round(score, 2),
            'lat': h_lat,
            'lon': h_lon
        })
        
    # Sort by score ascending
    ranked_df = pd.DataFrame(ranked_list)
    if not ranked_df.empty:
        ranked_df = ranked_df.sort_values('score')
        
    return ranked_df
