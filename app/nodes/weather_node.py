from app.state import GraphState
from app.weather import WeatherError, extract_facts, get_weather_for_city


async def fetch_weather(state: GraphState) -> dict:
    query = state.get("location_query")
    try:
        result = await get_weather_for_city(query)
    except WeatherError as e:
        return {"weather_error": str(e)}

    facts = extract_facts(result["forecast"])
    return {
        "location": result["location"],
        "forecast": result["forecast"],
        "facts": facts,
        "weather_error": None,
    }
