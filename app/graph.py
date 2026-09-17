from langgraph.graph import END, StateGraph

from app.nodes.compose import compose, compose_no_trigger
from app.nodes.extract import extract
from app.nodes.fallback import clarify, no_guidance, weather_failure
from app.nodes.intake import intake
from app.nodes.session_update import update_session
from app.nodes.sop_match import match_sop
from app.nodes.weather_node import fetch_weather
from app.state import GraphState


def has_location(state: GraphState) -> str:
    return "weather" if state.get("location_query") else "clarify"


def weather_ok(state: GraphState) -> str:
    return "failure" if state.get("weather_error") else "sop_match"


def sop_match_outcome(state: GraphState) -> str:
    return state.get("sop_match_status", "not_applicable")


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("intake", intake)
    graph.add_node("extract", extract)
    graph.add_node("weather", fetch_weather)
    graph.add_node("sop_match", match_sop)
    graph.add_node("compose", compose)
    graph.add_node("compose_no_trigger", compose_no_trigger)
    graph.add_node("clarify", clarify)
    graph.add_node("weather_failure", weather_failure)
    graph.add_node("no_guidance", no_guidance)
    graph.add_node("update_session", update_session)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "extract")
    graph.add_conditional_edges("extract", has_location, {"weather": "weather", "clarify": "clarify"})
    graph.add_conditional_edges("weather", weather_ok, {"sop_match": "sop_match", "failure": "weather_failure"})
    graph.add_conditional_edges(
        "sop_match",
        sop_match_outcome,
        {
            "matched": "compose",
            "evaluated_no_trigger": "compose_no_trigger",
            "not_applicable": "no_guidance",
        },
    )
    graph.add_edge("compose", "update_session")
    graph.add_edge("compose_no_trigger", "update_session")
    graph.add_edge("clarify", "update_session")
    graph.add_edge("weather_failure", "update_session")
    graph.add_edge("no_guidance", "update_session")
    graph.add_edge("update_session", END)

    return graph.compile()


_compiled = None


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


async def run_turn(session_id: str, message: str) -> str:
    graph = get_graph()
    result = await graph.ainvoke({"session_id": session_id, "message": message})
    return result["response"]


async def run_turn_full(session_id: str, message: str) -> dict:
    """Like run_turn but returns the whole final state, not just the reply
    text. Used by evals that need to assert on matched_ids / weather_error."""
    graph = get_graph()
    return await graph.ainvoke({"session_id": session_id, "message": message})
