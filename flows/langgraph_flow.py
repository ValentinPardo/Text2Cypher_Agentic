"""
LangGraph Flow - Orchestrates the Text2Cypher Agentic System.

This module builds a proper LangGraph StateGraph with nodes and edges to route
user queries through different agents (orchestrator, refiner, text2cypher, web_search, answerer).

Architecture:
    START -> orchestrator -> [refiner | text_to_cypher | web_search | answerer]
    refiner -> orchestrator
    text_to_cypher -> answerer
    web_search -> answerer
    answerer -> END
"""
from typing import Any, Dict
from langgraph.graph import StateGraph, START, END

# Import State and all node functions
from agents.contracts import State
from agents.orchestrator_agent import orchestrator_node, route_decision
from agents.refiner_agent import refiner_node
from agents.text2cypher_agent import text2cypher_node
from agents.web_search_agent import web_search_node
from agents.answerer_agent import answerer_node


def create_graph() -> StateGraph:
    """Create and configure the LangGraph StateGraph.
    
    Returns:
        Compiled StateGraph ready for execution
    """
    # Create the graph with State
    graph = StateGraph(State)
    
    # Add all nodes
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("refiner", refiner_node)
    graph.add_node("text_to_cypher", text2cypher_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("answerer", answerer_node)
    
    # Add edges
    # START -> orchestrator
    graph.add_edge(START, "orchestrator")
    
    # Conditional edges from orchestrator (using route_decision function)
    graph.add_conditional_edges(
        "orchestrator",
        route_decision,
        {
            "refiner": "refiner",
            "text_to_cypher": "text_to_cypher",
            "web_search": "web_search",
            "answerer": "answerer",
        }
    )
    
    # refiner -> orchestrator (refiner sends back to orchestrator for re-routing)
    graph.add_edge("refiner", "orchestrator")
    
    # text_to_cypher -> answerer
    graph.add_edge("text_to_cypher", "answerer")
    
    # web_search -> answerer
    graph.add_edge("web_search", "answerer")
    
    # answerer -> END
    graph.add_edge("answerer", END)
    
    # Compile the graph
    return graph.compile()


# Create the compiled graph once at module level
app = create_graph()


def run_flow(user_input: str, mock: bool = True) -> Dict[str, Any]:
    """Execute the LangGraph flow synchronously.
    
    Args:
        user_input: User's query or question
        mock: Whether to use mock mode (avoids real API calls)
        
    Returns:
        Final state dict with all fields including final_answer
    """
    import asyncio
    
    # Check if there's already an event loop running
    try:
        loop = asyncio.get_running_loop()
        # If we get here, we're already in an async context
        # This shouldn't happen for sync call, but handle it
        raise RuntimeError("run_flow should not be called from async context. Use run_flow_async instead.")
    except RuntimeError:
        # No event loop running, we can create one
        return asyncio.run(run_flow_async(user_input, mock))


async def run_flow_async(user_input: str, mock: bool = True) -> Dict[str, Any]:
    """Execute the LangGraph flow asynchronously.
    
    Args:
        user_input: User's query or question
        mock: Whether to use mock mode (avoids real API calls)
        
    Returns:
        Final state dict with all fields including final_answer
    """
    print(f"\n{'='*60}")
    print(f"🚀 Starting LangGraph Flow")
    print(f"   Query: {user_input}")
    print(f"   Mock: {mock}")
    print(f"{'='*60}\n")
    
    # Initialize state
    initial_state: State = {
        "query": user_input,
        "refined_query": None,
        "route_decision": None,
        "cypher_result": None,
        "web_result": None,
        "final_answer": None,
        "error": None,
        "iteration_count": 0,
        "mock": mock,
    }
    
    # Invoke the graph asynchronously
    final_state = await app.ainvoke(initial_state)
    
    print(f"\n{'='*60}")
    print(f"✅ LangGraph Flow Completed")
    print(f"   Final Answer: {final_state.get('final_answer', 'N/A')}")
    print(f"{'='*60}\n")
    
    return final_state


def visualize_graph(output_path: str = "graph.png"):
    """Generate a visual representation of the graph (requires pygraphviz).
    
    Args:
        output_path: Path to save the graph visualization
    """
    try:
        from IPython.display import Image, display
        display(Image(app.get_graph().draw_mermaid_png()))
    except Exception as e:
        print(f"Could not visualize graph: {e}")
        print("To visualize, install: pip install pygraphviz")


__all__ = ["create_graph", "run_flow", "run_flow_async", "app", "visualize_graph"]


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def main():
        # Test with a simple query
        result = await run_flow_async("Hola", mock=True)
        print(f"\nFinal Answer: {result.get('final_answer')}")
        
        # Test with a database query
        result = await run_flow_async("¿Cuáles son los top 5 productos?", mock=True)
        print(f"\nFinal Answer: {result.get('final_answer')}")
    
    asyncio.run(main())
