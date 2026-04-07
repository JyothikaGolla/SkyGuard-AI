import pandas as pd
import glob

files = glob.glob('real_flight_data/*.csv')
if files:
    df = pd.concat([pd.read_csv(f) for f in files])
    print(f'Total flights: {len(df)}')
    print(f'Unique aircraft: {df["icao24"].nunique()}')
    print(f'CSV files: {len(files)}')
else:
    print('No data files found')
