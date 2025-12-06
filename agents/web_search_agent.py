"""
Web Search Agent using Google Custom Search.

This node exposes an async `run(state: State) -> State` function that reads
`state['query']` and populates `state['web_result']` with a client-friendly
summary and raw results.

It no longer contains any mock-mode branches; if Google credentials are not
configured the node will return an empty results list and a user-friendly
message indicating no external data was found.
"""
from typing import Dict, Any, List
import os
import asyncio
from typing import Optional
from urllib.parse import urlparse

from agents.contracts import State

try:
    import requests
except Exception:
    requests = None


def _search_with_google(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Call Google Custom Search JSON API and return normalized results list."""
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

    top = results[:3]
    # Filter out entries with no useful text to avoid empty bullets
    filtered = []
    for r in top:
        title = (r.get("title") or "").strip()
        content = (r.get("content") or "").strip()
        url = (r.get("url") or "").strip()
        if title or content or url:
            filtered.append({"title": title or "(sin título)", "content": content, "url": url})

    lines = []
    lines.append(f"He encontrado {len(results)} resultados en la web para: '{question}'. Aquí un resumen de los más relevantes:")
    if not filtered:
        lines.append("No se encontraron extractos útiles en los resultados para resumir.")
    else:
        for i, r in enumerate(filtered, start=1):
            title = r.get("title", "(sin título)")
            url = r.get("url", "")
            content = r.get("content", "")
            snippet = content if len(content) <= 200 else content[:197] + "..."
            # Use parenthesis numbering to avoid sentence-splitting on '1.'
            if url:
                lines.append(f"{i}) {title} — {snippet} (ver: {url}).")
            else:
                lines.append(f"{i}) {title} — {snippet}.")

    lines.append("Si querés, puedo intentar obtener más detalles de alguna de estas fuentes o convertir esto en una respuesta más formal para un cliente.")
    return "\n".join(lines)


class WebSearchNode:
    """Nodo WebSearch con interfaz async `run(state: State) -> State`.

    Lee `state['query']` y escribe `state['web_result']`.
    """

    async def run(self, state: State) -> State:
        question = state.get("query", "")
        if not question:
            state["web_result"] = {
                "results": [],
                "result_count": 0,
                "success": False,
                "error": "missing 'query' in state",
                "user_friendly": "No se proporcionó ninguna consulta para buscar.",
            }
            return state

        max_results = int(state.get("max_results", 5))

        try:
            loop = asyncio.get_running_loop()
            results = []
            if os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CX") and requests is not None:
                results = await loop.run_in_executor(None, _search_with_google, question, max_results)

            # Optionally filter results by allowed domains for this application
            allowed = os.getenv("WEB_SEARCH_DOMAINS")
            filtered_results = results
            filtered_by_domain = True
            if allowed:
                allowed_set = [d.strip().lower() for d in allowed.split(",") if d.strip()]
                def _domain_ok(url: str) -> bool:
                    try:
                        netloc = urlparse(url).netloc.lower()
                    except Exception:
                        return False
                    for a in allowed_set:
                        if netloc.endswith(a):
                            return True
                    return False

                filtered_results = [r for r in results if r.get("url") and _domain_ok(r.get("url"))]
                if not filtered_results:
                    filtered_by_domain = False

            state["web_result"] = {
                "results": filtered_results,
                "result_count": len(filtered_results),
                "success": True,
                "error": None,
                "user_friendly": _format_user_friendly(question, filtered_results) if filtered_results else ("No se encontraron resultados en los dominios permitidos. Si querés, puedo ampliar la búsqueda fuera de esos dominios."),
                "_filtered_by_domain": filtered_by_domain,
                "_original_count": len(results),
            }
        except Exception as e:
            state["web_result"] = {
                "results": [],
                "result_count": 0,
                "success": False,
                "error": str(e),
                "user_friendly": f"Ocurrió un error al buscar en la web: {str(e)}",
            }
        return state


async def web_search_node(state: State) -> State:
    node = WebSearchNode()
    return await node.run(state)


async def web_search(question: str, max_results: int = 5) -> Dict[str, Any]:
    """Public helper that returns a client-friendly dict (no internal keys)."""
    node = WebSearchNode()
    state = {"query": question, "max_results": max_results, "iteration_count": 0}
    result_state = await node.run(state)
    res = result_state.get("web_result", {})
    return res


__all__ = ["WebSearchNode", "web_search_node", "web_search"]
