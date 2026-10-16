import httpx


async def get_weather(city: str) -> dict:
    """Fetch current conditions from Open-Meteo; no weather API key is required."""
    async with httpx.AsyncClient(timeout=10) as client:
        location = await client.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "en", "format": "json"})
        location.raise_for_status()
        places = location.json().get("results", [])
        if not places:
            return {"error": f"I could not find {city}."}
        place = places[0]
        current = await client.get("https://api.open-meteo.com/v1/forecast", params={"latitude": place["latitude"], "longitude": place["longitude"], "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"})
        current.raise_for_status()
        return {"city": place["name"], "country": place.get("country"), "current": current.json().get("current", {})}
