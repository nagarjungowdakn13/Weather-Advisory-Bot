"""Honest fallback responses. No LLM calls here — nothing to phrase, and
nothing to get wrong."""

from app.state import GraphState


async def clarify(state: GraphState) -> dict:
    return {
        "response": "I need a location to check the forecast — which city or area are you asking about?"
    }


async def weather_failure(state: GraphState) -> dict:
    reason = state.get("weather_error", "the weather service didn't return usable data")
    return {
        "response": (
            f"I couldn't get live weather data ({reason}). "
            "I'm not going to guess at conditions — try again in a bit, or double-check the location name."
        )
    }


async def no_guidance(state: GraphState) -> dict:
    facts = state.get("facts") or {}
    location = state.get("location") or {}
    name = location.get("name", "that location")
    facts_bits = ", ".join(f"{k}: {v}" for k, v in facts.items() if v is not None)
    return {
        "response": (
            f"I pulled current conditions for {name} ({facts_bits}), but I don't have a policy "
            "covering this specific question. I'd rather say that than guess at advice — "
            "let me know if you want the raw numbers or want to ask about something else."
        )
    }
