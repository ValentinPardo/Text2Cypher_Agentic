"""Agents package initialization.

This package contains all agents used in the LangGraph flow:
- OrchestratorNode: Routes queries to appropriate agents
- RefinerNode: Refines ambiguous queries
- Text2CypherNode: Converts natural language to Cypher queries
- WebSearchNode: Performs web searches
- AnswererNode: Formats final answers for users

Each agent has a corresponding node function for LangGraph integration.
"""

# Import node classes
from .orchestrator_agent import OrchestratorNode, orchestrator_node, route_decision
from .refiner_agent import RefinerNode, refiner_node
from .text2cypher_agent import Text2CypherNode, text2cypher_node
from .web_search_agent import WebSearchNode, web_search_node, web_search
from .answerer_agent import AnswererNode, answerer_node

# Import State contract
from .contracts import State

__all__ = [
    # State
    "State",
    # Node classes
    "OrchestratorNode",
    "RefinerNode",
    "Text2CypherNode",
    "WebSearchNode",
    "AnswererNode",
    # Node functions for LangGraph
    "orchestrator_node",
    "refiner_node",
    "text2cypher_node",
    "web_search_node",
    "answerer_node",
    "route_decision",
    # Legacy compatibility functions
    "web_search",
]
