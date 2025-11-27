"""
Minimal Web Search Agent for this project.

Uses Tavily (if `tavily` package is installed and `TAVILY_API_KEY` set).
Falls back to mock results when Tavily is not configured.

Public API:
 - web_search(question: str, max_results: int=5, use_mock: bool=False) -> dict

Response contract: {
  'question': str,
  'optimized_query': str,
  'results': list[{'title','url','content','score'}],
  'result_count': int,
  'success': bool,
  'error': Optional[str]
}
"""
from typing import Dict, Any, List
import os
import asyncio
from typing import Optional


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


def _search_with_tavily(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, max_results=max_results, search_depth="basic")
        results: List[Dict[str, Any]] = []
        for r in resp.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            })
        return results
    except ImportError:
        return []
    except Exception:
        return []


class WebSearchNode:
    """Nodo WebSearch con interfaz async `run(inputs: dict) -> dict`.

    Entrada esperada (inputs): {"query": str, "max_results": int (optional), "use_mock": bool (optional)}
    Salida: contrato idéntico al dict devuelto por la función `web_search` original.
    """

    def __init__(self, use_mock: Optional[bool] = None):
        # use_mock None => decide based on TAVILY_API_KEY
        self.use_mock = use_mock

    async def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        question = inputs.get("query") or inputs.get("question")
        if not question:
            return {
                "question": None,
                "optimized_query": None,
                "results": [],
                "result_count": 0,
                "success": False,
                "error": "missing 'query' in inputs",
            }

        max_results = int(inputs.get("max_results", inputs.get("maxResults", 5)))
        use_mock = inputs.get("use_mock") if inputs.get("use_mock") is not None else self.use_mock
        # If still None, derive from env
        if use_mock is None:
            use_mock = not bool(os.getenv("TAVILY_API_KEY"))

        try:
            optimized_query = question

            if use_mock:
                results = _mock_search(optimized_query)
            else:
                loop = asyncio.get_running_loop()
                results = await loop.run_in_executor(None, _search_with_tavily, optimized_query, max_results)

            return {
                "question": question,
                "optimized_query": optimized_query,
                "results": results,
                "result_count": len(results),
                "success": True,
                "error": None,
            }
        except Exception as e:
            return {
                "question": question,
                "optimized_query": None,
                "results": [],
                "result_count": 0,
                "success": False,
                "error": str(e),
            }


async def web_search(question: str, max_results: int = 5, use_mock: bool = False) -> Dict[str, Any]:
    """Compatibilidad con la API pública existente: llama internamente a `WebSearchNode`."""
    node = WebSearchNode(use_mock=use_mock)
    return await node.run({"query": question, "max_results": max_results, "use_mock": use_mock})


__all__ = ["WebSearchNode", "web_search"]
