"""
Contracts and State definition for LangGraph flow.

This module defines the State TypedDict that is shared across all nodes in the graph.
"""
from typing import TypedDict, Optional, Any, List, Dict


class State(TypedDict, total=False):
    """State shared across all nodes in the LangGraph flow.
    
    Fields:
        query: Original user query
        refined_query: Query after refinement by RefinerNode
        route_decision: Decision made by orchestrator (refiner, text_to_cypher, web_search, answerer)
        cypher_result: Results from Text2Cypher node (dict with cypher query and results)
        web_result: Results from WebSearch node (dict with search results)
        final_answer: Final formatted answer for the user
        error: Any error that occurred during processing
        iteration_count: Counter to prevent infinite loops
    """
    query: str
    refined_query: Optional[str]
    route_decision: Optional[str]
    cypher_result: Optional[Dict[str, Any]]
    web_result: Optional[Dict[str, Any]]
    final_answer: Optional[str]
    error: Optional[str]
    iteration_count: int
    


__all__ = ["State"]
