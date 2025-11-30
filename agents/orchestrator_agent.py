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
                prompt = f"Decide entre QUERY_DB, WEB_SEARCH para: {user_input}. Devuelve solo una palabra."
                resp = await client.generate_response([create_message(prompt)])
                decision = resp.get("content", "").strip().upper()
                # REFINE decision removed: map any refine intent to a DB query
                if "QUERY_DB" in decision: return "QUERY_DB"
                if "WEB_SEARCH" in decision: return "WEB_SEARCH"
            except Exception:
                pass
        # Default conservative: route to QUERY_DB (we already refine before deciding)
        return "QUERY_DB"

    async def orchestrate(self, user_input: str) -> Any:
        mock = self.use_mock_by_default
        print(f"\n🤖 [Orchestrator] Recibido: '{user_input}' (mock={mock})")

        # Primero: ejecutar el RefinerNode siempre y usar su output para la decisión
        try:
            refiner = self._get_refiner(mock)
            r = await refiner.run({"query": user_input})
            refined_query = r.get("refined_query") or r.get("error") or user_input
            print(f"✨ [Refiner] Consulta refinada (pre-decision): '{refined_query}'")
        except Exception as e:
            print(f"⚠️  [Refiner] Falló refinamiento inicial: {e}")
            refined_query = user_input

        # Decidir la ruta usando la consulta refinada
        route = await self.decide_route(refined_query)
        print(f"🔀 [Orchestrator] Decisión: {route}")

        if route == "QUERY_DB":
            print("   -> Enviando directo a Text2Cypher Node...")
            text_node = self._get_text2cypher(mock)
            # Usar la consulta refinada como entrada para la query a la DB
            result = await text_node.run({"query": refined_query, "mock": mock})
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
            else:
                top = web_result.get("results", [])[:3]
                snippets = []
                for item in top:
                    title = item.get("title", "")
                    content = item.get("content", "")
                    snippet = content if len(content) <= 500 else content[:497] + "..."
                    snippets.append(f"{title}: {snippet}")
                context_text = "\n".join(snippets)
                print(f"✨ Resultados de la busqueda web (desde WebSearch): '{web_result.get('user_friendly')}'")
            client = GeminiClient(config=LLMConfig(api_key=self.llm_api_key, model="gemini-2.0-flash-lite"))
            result = await client.generate_response([
                create_message(
                    f"Usando los siguientes resultados de búsqueda web como contexto, responde la siguiente pregunta de manera lo mas breve posible:\n\n"
                    f"Contexto:\n{context_text}\n\n"
                    f"Consulta original: {user_input}\n\n"
                    f"Devuelve solo la respuesta concisa si tenes los datos suficientes para responder, sino responde: 'No tengo suficiente información para responderte'."
                )
            ])
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
