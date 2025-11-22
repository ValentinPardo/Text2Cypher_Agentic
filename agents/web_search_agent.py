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
from concurrent.futures import ThreadPoolExecutor


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
        results = []
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


async def web_search(question: str, max_results: int = 5, use_mock: bool = False) -> Dict[str, Any]:
    """Async wrapper around web search; uses executor for blocking Tavily client calls."""
    try:
        optimized_query = question  # minimal strategy: no optimization step here

        if use_mock or not os.getenv("TAVILY_API_KEY"):
            results = _mock_search(optimized_query)
        else:
            loop = asyncio.get_running_loop()
            # Use a thread pool to avoid blocking the async event loop
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
