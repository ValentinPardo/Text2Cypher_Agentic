import os
from dotenv import load_dotenv
from typing import Any, Dict, Optional

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
    """Nodo Refiner con interfaz async `run(inputs: dict) -> dict`.

    Entrada esperada (inputs): {"query": str}
    Salida: {"refined_query": str} o {"error": str}

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

    async def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        user_query = inputs.get("query") or inputs.get("user_query")
        if not user_query:
            return {"error": "missing 'query' in inputs"}

        if self.mock:
            # Return a deterministic mock for local testing
            return {"refined_query": f"(MOCK) {user_query.strip()}"}

        llm = await self._get_llm()

        prompt = f"""
Sos un agente experto en "Refinamiento y Clasificación de Consultas".

Tu objetivo es analizar la pregunta del usuario y decidir:

## OPCIÓN A: CONSULTA A BASE DE DATOS
Si la pregunta se relaciona con datos de e-commerce (Productos, Clientes, Compras, Comunidades, Inventario, Pedidos, etc.):
- Reescribila para que sea clara, explícita y fácil de entender para un agente que genera código Cypher (Neo4j).
- Mantené la intención original del usuario.
- Si ya es clara, devolvela tal cual o con mínimas mejoras.
- Si es ambigua, inferí lo más probable en el contexto de e-commerce.

Formato de respuesta:
TIPO: BASE_DE_DATOS
CONSULTA_REFINADA: [tu consulta refinada aquí]

## OPCIÓN B: BÚSQUEDA WEB
Si la pregunta NO se relaciona con datos internos del e-commerce (preguntas generales, noticias, información externa, consultas que requieren conocimiento actualizado, etc.):

Formato de respuesta:
TIPO: BUSQUEDA_WEB
CONSULTA_ORIGINAL: [consulta del usuario]

---

EJEMPLOS:

Input: "cuales son los top productos"
Output:
TIPO: BASE_DE_DATOS
CONSULTA_REFINADA: Listar los 5 productos con mayor cantidad de ventas.

Input: "que cliente compro mas"
Output:
TIPO: BASE_DE_DATOS
CONSULTA_REFINADA: Identificar al cliente que ha realizado el mayor gasto total en compras.

Input: "quien gano el mundial 2022"
Output:
TIPO: BUSQUEDA_WEB
CONSULTA_ORIGINAL: quien gano el mundial 2022

Input: "cuantos productos tenemos en stock"
Output:
TIPO: BASE_DE_DATOS
CONSULTA_REFINADA: Obtener el conteo total de productos disponibles en inventario.

Input: "que es inteligencia artificial"
Output:
TIPO: BUSQUEDA_WEB
CONSULTA_ORIGINAL: que es inteligencia artificial

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
            return {"error": "LLM returned empty content"}

        refined = content.strip()
        return {"refined_query": refined}


async def run(inputs: Dict[str, Any], mock: bool = False) -> Dict[str, Any]:
    node = RefinerNode(mock=mock)
    return await node.run(inputs)


__all__ = ["RefinerNode", "run"]
