"""
forecast_availability.py
 
Predicts each hospital's bed/ICU availability for the next few time steps
(30 min, 60 min ahead) using the simulated history in availability_log.csv.
 
Approach (kept deliberately simple/explainable for a fresher project --
you can defend every step of this in an interview):
 
  1. Feature engineering per hospital:
       - hour of day, day of week, is_weekend
       - recent average (last 3 readings) -- captures short-term trend
       - lag features (value 1 step ago, 2 steps ago)
  2. Model: a separate lightweight regression per hospital
       (Linear Regression as baseline, RandomForestRegressor as upgrade)
  3. Output: for each hospital, predicted beds_available at t+30min and t+60min,
     plus a simple "trend" label: FILLING FAST / STABLE / FREEING UP
 
This file is standalone -- run it after simulate_availability.py.
It writes forecast_output.csv with one row per hospital.
"""
 
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
 
AVAILABILITY_CSV = "availability_log.csv"
HOSPITALS_CSV = "hospitals.csv"
OUTPUT_CSV = "forecast_output.csv"
 
TARGET_COL = "beds_available"   # could also run this for icu_available
N_LAGS = 3                      # how many past readings to use as features
STEPS_AHEAD = [1, 2]            # 1 step = 30 min, 2 steps = 60 min (matches sim interval)
 
TREND_THRESHOLD = 2             # beds difference to call it "filling fast" / "freeing up"
 
 
def build_features(df_hospital: pd.DataFrame, target_col: str) -> pd.DataFrame:
    """Given one hospital's time-sorted availability series, build a
    supervised-learning feature table with lag features + calendar features."""
    df = df_hospital.sort_values("timestamp").reset_index(drop=True).copy()
 
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
 
    for lag in range(1, N_LAGS + 1):
        df[f"lag_{lag}"] = df[target_col].shift(lag)
 
    df["recent_avg"] = df[[f"lag_{i}" for i in range(1, N_LAGS + 1)]].mean(axis=1)
 
    # Targets: value N steps ahead
    for step in STEPS_AHEAD:
        df[f"target_t+{step}"] = df[target_col].shift(-step)
 
    df = df.dropna().reset_index(drop=True)
    return df
 
 
def train_and_forecast_one_hospital(df_hospital, hospital_id, target_col=TARGET_COL):
    """Trains a model per forecast horizon for one hospital, returns latest
    prediction + a simple trend label."""
    feat_df = build_features(df_hospital, target_col)
 
    if len(feat_df) < 20:
        # not enough history to train reliably -- fall back to naive forecast
        latest_val = df_hospital.sort_values("timestamp")[target_col].iloc[-1]
        return {
            "hospital_id": hospital_id,
            "current": latest_val,
            "pred_30min": latest_val,
            "pred_60min": latest_val,
            "trend": "STABLE (insufficient history)",
            "mae_30min": None,
        }
 
    feature_cols = ["hour", "day_of_week", "is_weekend", "recent_avg"] + \
                    [f"lag_{i}" for i in range(1, N_LAGS + 1)]
 
    preds = {}
    maes = {}
 
    for step in STEPS_AHEAD:
        target_col_name = f"target_t+{step}"
        X = feat_df[feature_cols]
        y = feat_df[target_col_name]
 
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False  # keep time order for eval
        )
 
        model = RandomForestRegressor(n_estimators=80, max_depth=6, random_state=42)
        model.fit(X_train, y_train)
 
        y_pred_test = model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred_test)
        maes[step] = mae
 
        # Predict for the very latest available row (most recent real data)
        latest_row = feat_df.iloc[[-1]][feature_cols]
        pred = model.predict(latest_row)[0]
        preds[step] = max(0, round(pred))
 
    current_val = feat_df[target_col].iloc[-1] if target_col in feat_df.columns else df_hospital[target_col].iloc[-1]
    # current_val should come from raw target, not feature-shifted frame:
    current_val = df_hospital.sort_values("timestamp")[target_col].iloc[-1]
 
    pred_30 = preds.get(1, current_val)
    diff = pred_30 - current_val
    if diff <= -TREND_THRESHOLD:
        trend = "⚠️ FILLING FAST"
    elif diff >= TREND_THRESHOLD:
        trend = "🟢 FREEING UP"
    else:
        trend = "STABLE"
 
    return {
        "hospital_id": hospital_id,
        "current": current_val,
        "pred_30min": pred_30,
        "pred_60min": preds.get(2, pred_30),
        "trend": trend,
        "mae_30min": round(maes.get(1, np.nan), 2),
    }
 
 
def main():
    df = pd.read_csv(AVAILABILITY_CSV, parse_dates=["timestamp"])
    hospitals = pd.read_csv(HOSPITALS_CSV)
 
    results = []
    for hospital_id, group in df.groupby("hospital_id"):
        res = train_and_forecast_one_hospital(group, hospital_id)
        results.append(res)
 
    forecast_df = pd.DataFrame(results)
    forecast_df = forecast_df.merge(
        hospitals[["hospital_id", "name", "type"]], on="hospital_id"
    )
    forecast_df = forecast_df[[
        "hospital_id", "name", "type", "current", "pred_30min",
        "pred_60min", "trend", "mae_30min"
    ]]
 
    forecast_df.to_csv(OUTPUT_CSV, index=False)
    print(f"Forecasts written to {OUTPUT_CSV}\n")
    # print(forecast_df.to_string(index=False)) # Commented out to prevent UnicodeEncodeError in Windows terminal
    print(f"\nAvg MAE (30-min horizon) across hospitals: {forecast_df['mae_30min'].mean():.2f} beds")
 
 
if __name__ == "__main__":
    main()
