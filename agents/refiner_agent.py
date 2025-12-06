"""
Refiner Agent - Refines and clarifies user queries.

This agent takes ambiguous or vague queries and refines them to be more clear
and explicit for downstream agents (especially Text2Cypher).
"""
import os
import asyncio
from dotenv import load_dotenv
from typing import Any, Optional

from agents.contracts import State

load_dotenv(override=True)

# Optional import of the project's Gemini client; lazy-instantiated when needed.
try:
    from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
except Exception:
    GeminiClient = None  # type: ignore
    LLMConfig = None  # type: ignore

# Import helpers lazily inside run() to avoid hard dependency at module import time

GEMINI_API_KEY = os.getenv("LLM_API_KEY")


class RefinerNode:
    """Nodo Refiner con interfaz async `run(state: State) -> State`.
    
    Esta clase soporta `mock=True` para evitar llamadas reales al LLM durante pruebas.
    """

    def __init__(self, llm: Optional[Any] = None, model: str = "gemini-2.0-flash-lite", mock: bool = False):
        self._provided_llm = llm
        self.model = model
        self.mock = bool(mock)

    async def _get_llm(self) -> Any:
        if self._provided_llm is not None:
            return self._provided_llm
        if self.mock:
            return None
        if GeminiClient is None or LLMConfig is None:
            raise RuntimeError("Gemini client not available in environment")
        return GeminiClient(config=LLMConfig(api_key=GEMINI_API_KEY, model=self.model))

    async def run(self, state: State) -> State:
        """Refine the query in the state.
        
        Args:
            state: Current state with query
            
        Returns:
            Updated state with refined_query and incremented iteration_count
        """
        user_query = state.get("query", "")
        mock = state.get("mock", self.mock)
        iteration_count = state.get("iteration_count", 0)
        
        if not user_query:
            state["error"] = "missing 'query' in state"
            return state

        print(f"✨ [Refiner] Refining query: '{user_query}' (iteration={iteration_count})")

        if mock:
            # Return a deterministic mock for local testing
            state["refined_query"] = f"(REFINED) {user_query.strip()}"
            state["iteration_count"] = iteration_count + 1
            return state

        llm = await self._get_llm()

        prompt = f"""
Sos un agente experto en "Refinamiento de Consultas para E-commerce".

Tu objetivo es analizar la pregunta del usuario y refinarla para que sea clara, explícita y fácil de entender para un agente que genera código Cypher (Neo4j) sobre una base de datos de e-commerce.

Contexto de la base de datos:
- Productos (id, nombre, descripcion, precio, stock)
- Clientes (id, nombre, direccion, telefono, email)
- Compras (id, fecha, total)
- Comunidades (id, nombre, descripcion, tipo)
- Relaciones: Cliente REALIZÓ_COMPRA Compra, Compra INCLUYE Producto, Producto INVENTARIO Comunidad

Reglas para refinamiento:
1. Mantén la intención original del usuario
2. Si la consulta es vaga o ambigua, inferí lo más probable en el contexto de e-commerce
3. Si menciona "top", "mejor", "mayor", especifica un límite razonable (ej: top 5, top 10)
4. Si es sobre clientes/productos/ventas, clarifica qué información específica se busca
5. Si ya es clara, devolvela tal cual o con mínimas mejoras
6. Devuelve SOLO la consulta refinada, sin explicaciones adicionales

Ejemplos:

Input: "top productos"
Output: Listar los 5 productos con mayor cantidad de ventas.

Input: "que cliente compro mas"
Output: Identificar al cliente que ha realizado el mayor gasto total en compras.

Input: "productos en stock"
Output: Obtener todos los productos que tienen stock disponible (stock > 0).

Input: "info de ventas"
Output: Obtener información detallada de todas las compras realizadas, incluyendo fecha y total.

---

Input: "{user_query}"
Output:
""".format(user_query=user_query)

        # Enviar al LLM y obtener respuesta
        try:
            from helpers.llm_helper import create_message
        except Exception as e:  # pragma: no cover - fallback for environments lacking graphiti_core
            raise RuntimeError("helpers.llm_helper not available; cannot call LLM") from e

        response = await llm.generate_response([create_message(prompt)])

        # Normalizar respuesta
        content = None
        if isinstance(response, dict):
            content = response.get("content")
        else:
            content = getattr(response, "content", None)

        if not content:
            state["error"] = "LLM returned empty content"
            return state

        refined = content.strip()
        
        # Update state
        state["refined_query"] = refined
        state["iteration_count"] = iteration_count + 1
        
        print(f"✨ [Refiner] Refined to: '{refined}'")
        
        return state


async def refiner_node(state: State) -> State:
    """LangGraph node function for the refiner.
    
    This is the function that will be added to the LangGraph StateGraph.
    
    Args:
        state: Current state
        
    Returns:
        Updated state with refined_query
    """
    node = RefinerNode(mock=state.get("mock", False))
    return await node.run(state)


__all__ = ["RefinerNode", "refiner_node"]
