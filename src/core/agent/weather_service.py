import httpx
from typing import Dict, Any, Optional
from src.utils.logging import get_logger

logger = get_logger()

class WeatherService:
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    async def get_current_weather(self, lat: float, lon: float) -> Dict[str, Any]:
        """Fetch current weather from Open-Meteo for the given coordinates."""
        async with httpx.AsyncClient(timeout=8.0) as client:
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "precipitation",
                    "weather_code",
                    "wind_speed_10m",
                    "is_day",
                ],
                "timezone": "auto",
            }
            try:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                current = data.get("current", {})
                return {
                    "temperature": current.get("temperature_2m"),
                    "humidity": current.get("relative_humidity_2m"),
                    "precipitation": current.get("precipitation"),
                    "wind_speed": current.get("wind_speed_10m"),
                    "weather_code": current.get("weather_code"),
                    "is_day": current.get("is_day"),
                }
            except httpx.TimeoutException:
                logger.warning(f"Weather fetch timeout for ({lat}, {lon})")
                raise
            except Exception as e:
                logger.error(f"Weather fetch failed: {e}")
                raise