"""
Minimal Web Search Agent for this project.

Uses Google Custom Search API when `GOOGLE_API_KEY` and `GOOGLE_CX` are set.
Falls back to mock results when Google is not configured or unavailable.

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
    """Nodo WebSearch con interfaz async `run(inputs: dict) -> dict`.

    Entrada esperada (inputs): {"query": str, "max_results": int (optional), "use_mock": bool (optional)}
    Salida: contrato idéntico al dict devuelto por la función `web_search` original.
    """

    def __init__(self, use_mock: Optional[bool] = None):
        self.use_mock = use_mock

    async def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        question = inputs.get("query") or inputs.get("question")
        if not question:
            return {
                "question": None,
                "results": [],
                "result_count": 0,
                "success": False,
                "error": "missing 'query' in inputs",
            }

        max_results = int(inputs.get("max_results", inputs.get("maxResults", 5)))
        # use_mock = inputs.get("use_mock") if inputs.get("use_mock") is not None else self.use_mock
        # If still None, derive from env: use mock unless Google keys present and requests available
        #if use_mock is None:
        #    use_mock = not (bool(os.getenv("GOOGLE_API_KEY")) and bool(os.getenv("GOOGLE_CX")) and requests is not None)

        try:
            question

        #    if use_mock:
        #        results = _mock_search(question)
        #    else:
            # Use Google Custom Search (must be configured). If Google returns no results,
            loop = asyncio.get_running_loop()
            print("GOOGLE API KEYS PRESENT: " + str(bool(os.getenv("GOOGLE_API_KEY")) and bool(os.getenv("GOOGLE_CX")) and requests is not None))
            print("api key:" + os.getenv("GOOGLE_API_KEY"))
            if os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CX") and requests is not None:
                results = await loop.run_in_executor(None, _search_with_google, question, max_results)
            else:
                results = []
            #if not results:
            #    results = _mock_search(question)

            return {
                "question": question,
                "results": results,
                "result_count": len(results),
                "success": True,
                "error": None,
                # user-facing string summary of results
                "user_friendly": _format_user_friendly(question, results),
            }
        except Exception as e:
            return {
                "question": question,
                "results": [],
                "result_count": 0,
                "success": False,
                "error": str(e),
                "user_friendly": f"Ocurrió un error al buscar en la web: {str(e)}",
            }


async def web_search(question: str, max_results: int = 5, use_mock: bool = False) -> Dict[str, Any]:
    """Compatibilidad con la API pública existente: llama internamente a `WebSearchNode`."""
    node = WebSearchNode(use_mock=use_mock)
    res = await node.run({"query": question, "max_results": max_results, "use_mock": use_mock})
    # Strip internal-only fields before returning to clients. The Refiner node is
    # responsible for producing optimized queries, so don't expose them here.
    res.pop("optimized_query", None)
    # Optionally don't return the raw 'question' field to the client
    res.pop("question", None)
    return res


__all__ = ["WebSearchNode", "web_search"]
