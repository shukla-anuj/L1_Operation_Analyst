"""LangGraph definition for the analyzer workflow."""

from langgraph.graph import END, START, StateGraph

from .models import AnalyzerState
from .nodes import AnalyzerNodes


def build_analyzer_graph(nodes: AnalyzerNodes):
    graph = StateGraph(AnalyzerState)
    graph.add_node("extract_job_name", nodes.extract_job_name)
    graph.add_node("retrieve_support_manual", nodes.retrieve_support_manual)
    graph.add_node("extract_services", nodes.extract_services)
    graph.add_node("register_incident", nodes.register_incident)
    graph.add_node("retrieve_incidents", nodes.retrieve_incidents)
    graph.add_node("generate_initial_rca", nodes.generate_initial_rca)
    graph.add_node("retrieve_architecture", nodes.retrieve_architecture)
    graph.add_node("retrieve_logs", nodes.retrieve_logs)
    graph.add_node("generate_deep_rcas", nodes.generate_deep_rcas)
    graph.add_node("finalize", nodes.finalize)
    graph.add_edge(START, "extract_job_name")
    graph.add_edge("extract_job_name", "retrieve_support_manual")
    graph.add_edge("retrieve_support_manual", "extract_services")
    graph.add_edge("extract_services", "register_incident")
    graph.add_edge("register_incident", "retrieve_incidents")
    graph.add_edge("retrieve_incidents", "generate_initial_rca")
    graph.add_conditional_edges("generate_initial_rca", nodes.route_after_initial, {"finalize": "finalize", "deep_analysis": "retrieve_architecture"})
    graph.add_edge("retrieve_architecture", "retrieve_logs")
    graph.add_edge("retrieve_logs", "generate_deep_rcas")
    graph.add_edge("generate_deep_rcas", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()
