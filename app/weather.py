"""Open-Meteo client: geocoding + forecast. No API key needed."""

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_FIELDS = [
    "temperature_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "precipitation",
    "uv_index",
    "relative_humidity_2m",
]
HOURLY_FIELDS = [
    "temperature_2m",
    "precipitation_probability",
    "precipitation",
    "wind_speed_10m",
    "uv_index",
]
DAILY_FIELDS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "uv_index_max",
    "wind_speed_10m_max",
]


class WeatherError(Exception):
    """Raised for any geocoding or forecast failure. Message is user-safe."""


class LocationNotFound(WeatherError):
    pass


async def geocode(city: str) -> dict:
    """Resolve a city name to lat/lon. Raises LocationNotFound if nothing matches."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(GEOCODE_URL, params={"name": city, "count": 1})
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise WeatherError(f"geocoding service unreachable: {e}") from e

    data = resp.json()
    results = data.get("results") or []
    if not results:
        raise LocationNotFound(f"no location found matching '{city}'")

    top = results[0]
    return {
        "name": top["name"],
        "country": top.get("country", ""),
        "latitude": top["latitude"],
        "longitude": top["longitude"],
    }


async def fetch_forecast(latitude: float, longitude: float) -> dict:
    """Pull current + hourly + daily fields for a coordinate. Raises WeatherError on failure."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(CURRENT_FIELDS),
        "hourly": ",".join(HOURLY_FIELDS),
        "daily": ",".join(DAILY_FIELDS),
        "timezone": "auto",
        "forecast_days": 2,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise WeatherError(f"forecast service unreachable: {e}") from e

    data = resp.json()
    if "current" not in data:
        raise WeatherError("forecast response missing current conditions")
    return data


async def get_weather_for_city(city: str) -> dict:
    """Geocode then fetch forecast, bundled with the resolved location."""
    location = await geocode(city)
    forecast = await fetch_forecast(location["latitude"], location["longitude"])
    return {"location": location, "forecast": forecast}


def extract_facts(forecast: dict) -> dict:
    """Flatten current + today's daily fields into the numeric fact set
    SOP trigger conditions are written against. Every value here is real
    output from Open-Meteo, never LLM-generated."""
    current = forecast.get("current", {})
    daily = forecast.get("daily", {})

    def first_daily(key):
        values = daily.get(key) or []
        return values[0] if values else None

    return {
        "temperature_2m": current.get("temperature_2m"),
        "wind_speed_10m": current.get("wind_speed_10m"),
        "wind_gusts_10m": current.get("wind_gusts_10m"),
        "precipitation": current.get("precipitation"),
        "uv_index": current.get("uv_index"),
        "relative_humidity_2m": current.get("relative_humidity_2m"),
        "temperature_2m_max": first_daily("temperature_2m_max"),
        "temperature_2m_min": first_daily("temperature_2m_min"),
        "precipitation_probability_max": first_daily("precipitation_probability_max"),
        "uv_index_max": first_daily("uv_index_max"),
        "wind_speed_10m_max": first_daily("wind_speed_10m_max"),
    }
