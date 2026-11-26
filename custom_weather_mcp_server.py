import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import requests

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

mcp = FastMCP("Weather MCP Server")

REQUEST_TIMEOUT_SECONDS = 20


def _get_api_key() -> str:
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENWEATHER_API_KEY is missing "
            "from the project .env file."
        )
    return api_key


def _request_json(
    url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    try:
        response = requests.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        details = ""
        failed_response = getattr(exc, "response", None)
        if failed_response is not None:
            details = f" Response: {failed_response.text[:500]}"
        raise RuntimeError(
            f"OpenWeather request failed: {exc}.{details}"
        ) from exc


@mcp.tool()
def get_current_weather(
    city: str,
) -> dict[str, Any]:
    """Return the current weather for a city."""
    clean_city = city.strip()
    if not clean_city:
        raise ValueError("city cannot be empty")

    data = _request_json(
        "https://api.openweathermap.org/data/2.5/weather",
        {
            "q": clean_city,
            "appid": _get_api_key(),
            "units": "metric",
        },
    )

    main = data.get("main") or {}
    weather_list = data.get("weather") or [{}]
    first_weather = weather_list[0] if isinstance(weather_list[0], dict) else {}
    wind = data.get("wind") or {}

    return {
        "city": data.get("name", clean_city),
        "temperature_c": main.get("temp"),
        "feels_like_c": main.get("feels_like"),
        "humidity": main.get("humidity"),
        "condition": first_weather.get("description", ""),
        "wind_speed": wind.get("speed"),
    }


@mcp.tool()
def get_forecast(
    city: str,
) -> dict[str, Any]:
    """
    Return the first five three-hour
    forecast entries for a city.
    """
    clean_city = city.strip()
    if not clean_city:
        raise ValueError("city cannot be empty")

    data = _request_json(
        "https://api.openweathermap.org/data/2.5/forecast",
        {
            "q": clean_city,
            "appid": _get_api_key(),
            "units": "metric",
        },
    )

    forecast = []
    for item in (data.get("list") or [])[:5]:
        item_main = item.get("main") or {}
        item_weather_list = item.get("weather") or [{}]
        item_weather = (
            item_weather_list[0]
            if isinstance(item_weather_list[0], dict)
            else {}
        )
        forecast.append(
            {
                "datetime": item.get("dt_txt", ""),
                "temperature_c": item_main.get("temp"),
                "condition": item_weather.get("description", ""),
            }
        )

    city_info = data.get("city") or {}
    return {
        "city": city_info.get("name", clean_city),
        "forecast": forecast,
    }


if __name__ == "__main__":
    # mcp_client.py launches this as a stdio subprocess.
    mcp.run(
        transport="stdio",
    )