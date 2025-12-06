"""
Minimal Web Search Agent for this project.

Uses Google Custom Search API when `GOOGLE_API_KEY` and `GOOGLE_CX` are set.
Falls back to mock results when Google is not configured or unavailable.
"""
from typing import Dict, Any, List
import os
import asyncio
from typing import Optional

from agents.contracts import State

try:
    import requests
except Exception:
    requests = None


def _mock_search(query: str) -> List[Dict[str, Any]]:
    return [
        {
            "title": f"Mock Result 1 for '{query}'",
            "url": "https://example.com/result1",
            "content": f"This is a mock search result for the query: {query}.",
            "score": 0.95,
        },
        {
            "title": f"Mock Result 2 for '{query}'",
            "url": "https://example.com/result2",
            "content": f"Another mock result for: {query}.",
            "score": 0.87,
        },
    ]

def _search_with_google(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Use Google Custom Search JSON API to perform a web search.

    Requires `GOOGLE_API_KEY` and `GOOGLE_CX` set in env.
    Returns a list of dicts with keys: title, url, content, score.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    cx = os.getenv("GOOGLE_CX")
    if not api_key or not cx or requests is None:
        return []

    try:
        params = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": min(max_results, 10),
        }
        resp = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        results: List[Dict[str, Any]] = []
        for i, it in enumerate(items[:max_results]):
            title = it.get("title", "")
            link = it.get("link", "")
            snippet = it.get("snippet", "")
            # score: use -rank or rely on order (higher first)
            score = 1.0 - (i * 0.01)
            results.append({
                "title": title,
                "url": link,
                "content": snippet,
                "score": score,
            })
        return results
    except Exception:
        return []


def _format_user_friendly(question: str, results: List[Dict[str, Any]]) -> str:
    """Create a concise, user-facing Spanish response summarizing web search results."""
    if not results:
        return f"No encontré información relevante en la web sobre '{question}'. Puedo intentar buscar nuevamente o ayudarte con otra consulta."

    # Build a short human-friendly summary using top 1-3 results
    top = results[:3]
    lines = []
    lines.append(f"He encontrado {len(results)} resultados en la web para: '{question}'. Aquí un resumen de los más relevantes:")
    for i, r in enumerate(top, start=1):
        title = r.get("title", "(sin título)")
        url = r.get("url", "")
        content = r.get("content", "").strip()
        snippet = content if len(content) <= 200 else content[:197] + "..."
        if url:
            lines.append(f"{i}. {title} — {snippet} (ver: {url})")
        else:
            lines.append(f"{i}. {title} — {snippet}")

    lines.append("Si querés, puedo intentar obtener más detalles de alguna de estas fuentes o convertir esto en una respuesta más formal para un cliente.")
    return "\n".join(lines)


class WebSearchNode:
    """Nodo WebSearch con interfaz async `run(state: State) -> State`."""

    def __init__(self, use_mock: Optional[bool] = None):
        self.use_mock = use_mock

    async def run(self, state: State) -> State:
        """Process state and perform web search.
        
        Args:
            state: Current state with query
            
        Returns:
            Updated state with web_result
        """
        question = state.get("query", "")
        if not question:
            state["web_result"] = {
                "question": None,
                "results": [],
                "result_count": 0,
                "success": False,
                "error": "missing 'query' in state",
            }
            return state

        max_results = 5  # Default
        mock = state.get("mock", False)
        
        print(f"🌐 [WebSearch] Searching for: '{question}' (mock={mock})")

        try:
            # If mock mode, use mock results
            if mock:
                results = _mock_search(question)
            else:
                # Use Google Custom Search (must be configured). If Google returns no results,
                loop = asyncio.get_running_loop()
                if os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CX") and requests is not None:
                    results = await loop.run_in_executor(None, _search_with_google, question, max_results)
                else:
                    print("⚠️  [WebSearch] Google API keys not configured, using mock results")
                    results = _mock_search(question)

            state["web_result"] = {
                "question": question,
                "results": results,
                "result_count": len(results),
                "success": True,
                "error": None,
                # user-facing string summary of results
                "user_friendly": _format_user_friendly(question, results),
            }
            print(f"✅ [WebSearch] Found {len(results)} result(s)")
        except Exception as e:
            state["web_result"] = {
                "question": question,
                "results": [],
                "result_count": 0,
                "success": False,
                "error": str(e),
                "user_friendly": f"Ocurrió un error al buscar en la web: {str(e)}",
            }
            print(f"❌ [WebSearch] Error: {e}")
        
        return state


async def web_search_node(state: State) -> State:
    """LangGraph node function for web search.
    
    This is the function that will be added to the LangGraph StateGraph.
    
    Args:
        state: Current state
        
    Returns:
        Updated state with web_result
    """
    node = WebSearchNode(use_mock=state.get("mock", False))
    return await node.run(state)


async def web_search(question: str, max_results: int = 5, use_mock: bool = False) -> Dict[str, Any]:
    """Compatibilidad con la API pública existente: llama internamente a `WebSearchNode`."""
    node = WebSearchNode(use_mock=use_mock)
    state = {"query": question, "mock": use_mock, "iteration_count": 0}
    result_state = await node.run(state)
    res = result_state.get("web_result", {})
    # Strip internal-only fields before returning to clients
    res.pop("optimized_query", None)
    res.pop("question", None)
    return res


__all__ = ["WebSearchNode", "web_search_node", "web_search"]
