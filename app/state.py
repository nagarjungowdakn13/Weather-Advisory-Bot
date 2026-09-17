"""Shared state shape passed between graph nodes."""

from typing import TypedDict


class GraphState(TypedDict, total=False):
    session_id: str
    message: str
    turns: list[dict]
    decision_log: dict

    location_query: str | None
    activity: str | None
    is_followup: bool

    location: dict | None
    forecast: dict | None
    facts: dict | None
    weather_error: str | None

    candidate_ids: list[str]
    matched_ids: list[str]
    matched_reasoning: str

    response: str
