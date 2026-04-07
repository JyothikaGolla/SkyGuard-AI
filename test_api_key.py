"""
Quick test script to verify OpenWeatherMap API key activation
"""
import requests
import os

# Load API key from .env file
api_key = None
try:
    # Try to read from .env file directly
    with open('.env', 'r') as f:
        for line in f:
            if line.startswith('OPENWEATHER_API_KEY='):
                api_key = line.split('=', 1)[1].strip()
                break
except FileNotFoundError:
    pass

# Fallback to environment variable
if not api_key:
    api_key = os.getenv('OPENWEATHER_API_KEY')

# If still not found, use the key directly
if not api_key:
    api_key = '05de6f7b173617ac6eaafcf991f5b5da'

print("=" * 60)
print("OpenWeatherMap API Key Activation Test")
print("=" * 60)
print(f"\nAPI Key: {api_key[:8]}...{api_key[-4:]}")
print(f"Testing with coordinates: New Delhi (28.6139, 77.2090)")
print("\nAttempting API call...")

# Test API call
url = "https://api.openweathermap.org/data/2.5/weather"
params = {
    'lat': 28.6139,
    'lon': 77.2090,
    'appid': api_key,
    'units': 'metric'
}

try:
    print(f"\nRequest URL: {url}")
    print(f"Parameters: lat={params['lat']}, lon={params['lon']}, units={params['units']}")
    
    response = requests.get(url, params=params, timeout=10)
    
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n✅ SUCCESS! API key is ACTIVATED and working!")
        print("\nWeather Data Retrieved:")
        print(f"  Location: {data.get('name', 'N/A')}")
        print(f"  Temperature: {data['main']['temp']}°C")
        print(f"  Condition: {data['weather'][0]['main']}")
        print(f"  Description: {data['weather'][0]['description']}")
        print(f"  Humidity: {data['main']['humidity']}%")
        print(f"  Wind Speed: {data['wind']['speed']} m/s")
        print(f"  Visibility: {data.get('visibility', 'N/A')} meters")
        print("\n🎉 Your weather integration is ready to use!")
        
    elif response.status_code == 401:
        error_data = response.json()
        print("\n❌ AUTHENTICATION FAILED")
        print(f"  Message: {error_data.get('message', 'Invalid API key')}")
        print("\n⏳ Your API key is NOT YET activated.")
        print("   Please wait a couple of hours and try again.")
        print("   You can run this test again with: python test_api_key.py")
        
    else:
        print(f"\n⚠️ Unexpected response: {response.status_code}")
        print(f"  Response: {response.text}")
        
except requests.exceptions.Timeout:
    print("\n⚠️ Request timed out. Check your internet connection.")
    
except requests.exceptions.ConnectionError:
    print("\n⚠️ Connection error. Check your internet connection.")
    
except Exception as e:
    print(f"\n❌ Error: {str(e)}")

print("\n" + "=" * 60)
