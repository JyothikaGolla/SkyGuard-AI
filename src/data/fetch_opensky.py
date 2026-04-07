import requests
import pandas as pd
from datetime import datetime

# Default bounding box: rough India region (lat_min, lat_max, lon_min, lon_max)
DEFAULT_BBOX = (6, 38, 68, 98)

def fetch_flights(bbox=DEFAULT_BBOX):
    """Fetch live flights from OpenSky within the given bounding box.

    bbox: (min_lat, max_lat, min_lon, max_lon)
    """
    lamin, lamax, lomin, lomax = bbox
    url = (
        "https://opensky-network.org/api/states/all"
        f"?lamin={lamin}&lamax={lamax}&lomin={lomin}&lomax={lomax}"
    )

    res = requests.get(url, timeout=15)
    if res.status_code != 200:
        raise RuntimeError(f"Error fetching flights: {res.status_code} {res.text}")

    payload = res.json()
    states = payload.get("states", []) or []

    columns = [
        "icao24", "callsign", "origin_country", "time_position", "last_contact",
        "lon", "lat", "baro_altitude", "on_ground", "velocity", "heading",
        "vertical_rate", "sensors", "geo_altitude", "squawk",
        "spi", "position_source"
    ]

    df = pd.DataFrame(states, columns=columns)
    df["timestamp"] = datetime.utcnow()

    # Clean up some columns
    df["callsign"] = df["callsign"].fillna("").str.strip()
    df["geo_altitude"] = df["geo_altitude"].fillna(df["baro_altitude"])
    return df

if __name__ == "__main__":
    df = fetch_flights()
    print(df.head())
    print(f"Fetched {len(df)} flights")
