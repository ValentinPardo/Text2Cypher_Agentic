import asyncio
import os
from typing import Dict, Any

from agents.refiner_agent import RefinerNode
from agents.web_search_agent import WebSearchNode
from agents.text2cypher_agent import Text2CypherNode

try:
    # optional LLM decision support
    from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
    from helpers.llm_helper import create_message
    _LLM_AVAILABLE = True
except Exception:
    _LLM_AVAILABLE = False


class Orchestrator:
    """Orquestador que conecta Refiner, WebSearch y Text2Cypher nodes.

    Usa `mock=True` por defecto (si no hay llm/keys) para pruebas locales sin servicios externos.
    """

    def __init__(self, llm_api_key: str = None):
        self.llm_api_key = llm_api_key or os.getenv("LLM_API_KEY")
        self.use_mock_by_default = not bool(self.llm_api_key)

        # instantiate nodes lazily
        self.refiner_node = None
        self.web_node = None
        self.text2cypher_node = None

    def _get_refiner(self, mock: bool):
        if self.refiner_node is None:
            self.refiner_node = RefinerNode(mock=mock)
        return self.refiner_node

    def _get_web(self, use_mock: bool):
        if self.web_node is None:
            self.web_node = WebSearchNode(use_mock=use_mock)
        return self.web_node

    def _get_text2cypher(self, mock: bool):
        if self.text2cypher_node is None:
            self.text2cypher_node = Text2CypherNode(mock=mock)
        return self.text2cypher_node

    async def decide_route(self, user_input: str) -> str:
        """Decide la ruta: intenta usar un LLM si está disponible, sino heurística simple."""
        # If LLM integration is available, ask it (non-blocking call expected by user)
        if _LLM_AVAILABLE and self.llm_api_key:
            try:
                client = GeminiClient(config=LLMConfig(api_key=self.llm_api_key, model="gemini-2.0-flash-lite"))
                prompt = f"Decide entre REFINE, QUERY_DB, WEB_SEARCH, ANSWER para: {user_input}. Devuelve solo una palabra."
                resp = await client.generate_response([create_message(prompt)])
                decision = resp.get("content", "").strip().upper()
                if "REFINE" in decision: return "REFINE"
                if "QUERY_DB" in decision: return "QUERY_DB"
                if "WEB_SEARCH" in decision: return "WEB_SEARCH"
                if "ANSWER" in decision: return "ANSWER"
            except Exception:
                pass

        # Heurística fallback
        text = user_input.lower()
        greetings = ["hola", "buen", "gracias", "buenas"]
        if any(g in text for g in greetings):
            return "ANSWER"
        web_indicators = ["noticia", "tendencia", "último", "actualidad", "hoy", "202", "qué es", "qué son", "opinión"]
        if any(w in text for w in web_indicators):
            return "WEB_SEARCH"
        # If the user asks for very structured SQL-like phrases or mentions fields, route to QUERY_DB
        if any(k in text for k in ["listar", "mostrar", "top", "cantidad", "total", "ordenar"]):
            return "REFINE"

        # Default conservative: REFINE to improve quality
        return "REFINE"

    async def orchestrate(self, user_input: str) -> Any:
        mock = self.use_mock_by_default
        print(f"\n🤖 [Orchestrator] Recibido: '{user_input}' (mock={mock})")

        route = await self.decide_route(user_input)
        print(f"🔀 [Orchestrator] Decisión: {route}")

        if route == "ANSWER":
            # Simple canned responses when in mock mode
            if mock:
                return "Hola — soy un asistente de consultas de la base de datos."
            # If LLM available, generate a short friendly reply
            if _LLM_AVAILABLE and self.llm_api_key:
                client = GeminiClient(config=LLMConfig(api_key=self.llm_api_key, model="gemini-2.0-flash-lite"))
                prompt = f"El usuario dijo: '{user_input}'. Respondé brevemente como asistente de base de datos."
                resp = await client.generate_response([create_message(prompt)])
                return resp.get("content", "").strip()
            return "OK"

        if route == "REFINE":
            print("   -> Enviando a Refiner Node...")
            refiner = self._get_refiner(mock)
            r = await refiner.run({"query": user_input})
            refined_query = r.get("refined_query") or r.get("error")
            print(f"✨ [Refiner] Consulta refinada: '{refined_query}'")

            print("   -> Enviando a Text2Cypher Node...")
            text_node = self._get_text2cypher(mock)
            result = await text_node.run({"query": refined_query, "mock": mock})
            return result

        if route == "QUERY_DB":
            print("   -> Enviando directo a Text2Cypher Node...")
            text_node = self._get_text2cypher(mock)
            result = await text_node.run({"query": user_input, "mock": mock})
            return result

        if route == "WEB_SEARCH":
            print("   -> Realizando búsqueda web...")
            web_node = self._get_web(use_mock=mock)
            web_result = await web_node.run({"query": user_input, "max_results": 3})
            if not web_result.get("success"):
                print(f"⚠️  [WebSearch] Falló la búsqueda: {web_result.get('error')}")
                # fallback to refining the raw input
                refiner = self._get_refiner(mock)
                r = await refiner.run({"query": user_input})
                refined_query = r.get("refined_query")
            else:
                top = web_result.get("results", [])[:3]
                snippets = []
                for item in top:
                    title = item.get("title", "")
                    content = item.get("content", "")
                    snippet = content if len(content) <= 500 else content[:497] + "..."
                    snippets.append(f"{title}: {snippet}")
                context_text = "\n".join(snippets)
                user_with_context = f"{user_input}\n\nContexto (web):\n{context_text}"
                refiner = self._get_refiner(mock)
                r = await refiner.run({"query": user_with_context})
                refined_query = r.get("refined_query")

            print(f"✨ [Refiner] Consulta refinada (desde WebSearch): '{refined_query}'")
            print("   -> Enviando a Text2Cypher Node...")
            text_node = self._get_text2cypher(mock)
            result = await text_node.run({"query": refined_query, "mock": mock})
            return result


if __name__ == "__main__":
    async def main():
        orchestrator = Orchestrator()
        while True:
            user_input = input("\n👤 Tu pregunta (o 'salir'): ")
            if user_input.lower() in ["salir", "exit"]:
                break
            out = await orchestrator.orchestrate(user_input)
            print("\n--- Resultado final ---")
            print(out)

    asyncio.run(main())
