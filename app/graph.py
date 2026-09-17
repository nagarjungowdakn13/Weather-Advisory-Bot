from langgraph.graph import END, StateGraph

from app.nodes.compose import compose
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


def any_matched(state: GraphState) -> str:
    return "compose" if state.get("matched_ids") else "none"


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("intake", intake)
    graph.add_node("extract", extract)
    graph.add_node("weather", fetch_weather)
    graph.add_node("sop_match", match_sop)
    graph.add_node("compose", compose)
    graph.add_node("clarify", clarify)
    graph.add_node("weather_failure", weather_failure)
    graph.add_node("no_guidance", no_guidance)
    graph.add_node("update_session", update_session)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "extract")
    graph.add_conditional_edges("extract", has_location, {"weather": "weather", "clarify": "clarify"})
    graph.add_conditional_edges("weather", weather_ok, {"sop_match": "sop_match", "failure": "weather_failure"})
    graph.add_conditional_edges("sop_match", any_matched, {"compose": "compose", "none": "no_guidance"})
    graph.add_edge("compose", "update_session")
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
