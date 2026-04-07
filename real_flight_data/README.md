# Real Flight Data Collection

This directory stores real flight data collected from OpenSky Network API.

## Contributors

- Karthika Natarajan
- K Aravind
- Golla Jyothika

## Files

Each CSV file contains a batch of flights with weather data:
- Format: `{region}_{timestamp}.csv`
- Example: `india_20260107_143000.csv`

## Collection

To collect real flight data:

```bash
# Collect globally (no region restriction) - RECOMMENDED
python collect_real_data.py --requests 5 --delay 60

# Or explicitly use global flag
python collect_real_data.py --global --requests 5

# Collect from ALL regions (10 regions x 5 requests = 50 total)
python collect_real_data.py --region all --requests 5 --delay 60

# Collect from specific region
python collect_real_data.py --region india --requests 5
python collect_real_data.py --region europe --requests 10

# Available regions:
# india, usa_east, usa_west, europe, china, japan, 
# australia, south_america, middle_east, africa
```

## Usage in Training

Once you have collected data, train with it:

```bash
# Mix 30% real + 70% synthetic (default)
python train_models.py --use-real-data

# Mix 50% real + 50% synthetic
python train_models.py --use-real-data --real-ratio 0.5
```

## Data Accumulation

- Data accumulates over time across multiple runs
- Each collection adds to the existing dataset
- No duplicates are removed (by design - time series data)

Dataset preparation and collection workflow maintained by: Karthika Natarajan, K Aravind, Golla Jyothika.

## API Limits

Remember OpenSky API limits:
- ~100 requests per hour
- 30-60 seconds recommended between requests
- Be patient and respectful of the free API!
