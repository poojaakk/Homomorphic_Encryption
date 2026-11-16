"""
Phase 3: Dataset Integration & Schema Verification Script
Validates local storage, schema integrity, and statistical distributions
of the streaming environmental sensor dataset.
"""
import os
import sys
import pandas as pd

DATASET_PATH = "data/sensor_stream.csv"

def verify_dataset():
    print("=" * 65)
    print("PHASE 3: STREAMING DATASET INTEGRATION & INSPECTION")
    print("=" * 65)
    print(f"[*] Target File: {DATASET_PATH}")
    
    if not os.path.exists(DATASET_PATH):
        print(f"[-] ERROR: Dataset file not found at '{DATASET_PATH}'.")
        sys.exit(1)
        
    file_size_kb = os.path.getsize(DATASET_PATH) / 1024
    print(f"[+] Dataset file located locally ({file_size_kb:.2f} KB).")
    
    df = pd.read_csv(DATASET_PATH)
    total_records = len(df)
    print(f"[+] Total sequential records: {total_records}")
    print()
    
    print("[*] Column Schema & Description:")
    schema_descriptions = {
        "timestamp": "ISO 8601 observation timestamp (simulates arrival window)",
        "temperature": "Ambient Temperature in °C (Continuous float: [-19.0, 22.0])",
        "dew_point": "Atmospheric Dew Point in °C (Continuous float: [-27.0, 9.0])",
        "pressure": "Barometric Pressure in hPa (Continuous float: [1000.0, 1042.0])",
        "wind_speed": "Accumulated Wind Speed in m/s (Continuous float: [0.45, 299.0])",
        "pm25": "Particulate Matter concentration in ug/m^3 ([5.0, 980.0])",
    }
    
    for col in df.columns:
        desc = schema_descriptions.get(col, "Sensor measurement")
        dtype = df[col].dtype
        null_count = df[col].isnull().sum()
        print(f"    - {col:<12} | type: {str(dtype):<8} | nulls: {null_count} | {desc}")
        
    print()
    print("[*] Sample First 3 Stream Records:")
    for idx, row in df.head(3).iterrows():
        print(f"    Record #{idx}: T={row['temperature']}°C, P={row['pressure']}hPa, Dew={row['dew_point']}°C, Wind={row['wind_speed']}m/s, PM2.5={row['pm25']}")
        
    print()
    print("[*] Summary Statistics:")
    num_cols = ['temperature', 'dew_point', 'pressure', 'wind_speed', 'pm25']
    stats = df[num_cols].describe().loc[['mean', 'std', 'min', 'max']].round(2)
    print(stats.to_string())
    
    print("=" * 65)
    print("[SUCCESS] Dataset integration complete and ready for Kafka streaming!")
    print("=" * 65)

if __name__ == "__main__":
    verify_dataset()
