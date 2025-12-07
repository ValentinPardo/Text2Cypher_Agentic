# Standard imports
import os
import re
from dotenv import load_dotenv
from typing import Any, Dict, Optional

from agents.contracts import State

load_dotenv(override=True)

# Try to import optional dependencies; allow module to import even if they're missing (for tests).
try:
    from neo4j import AsyncGraphDatabase
except Exception:
    AsyncGraphDatabase = None  # type: ignore

try:
    from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
    from helpers.llm_helper import create_message
except Exception:
    GeminiClient = None  # type: ignore
    LLMConfig = None  # type: ignore

# -------------------------
# CONFIG
# -------------------------

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS")

GEMINI_API_KEY = os.getenv("LLM_API_KEY")
# -----------------------
# Esquema para el agente
# -----------------------

GRAPH_SCHEMA = """
NODOS DISPONIBLES Y SUS PROPIEDADES:

(Producto):
  - id
  - nombre
  - descripcion
  - precio
  - stock

(Cliente):
  - id
  - nombre
  - direccion
  - telefono
  - email

(Compra):
  - id
  - fecha
  - total

(Comunidad):
  - id
  - nombre
  - descripcion
  - tipo

RELACIONES DISPONIBLES:

(:Cliente)-[:REALIZÓ_COMPRA]->(:Compra)
(:Compra)-[:INCLUYE {cantidad}]->(:Producto)
(:Producto)-[:INVENTARIO]->(:Comunidad)

REGLAS:
1. No inventes propiedades ni relaciones.
2. Si no se puede responder con los datos existentes, devolvé "NO_CYPHER".
3. No acepto múltiples consultas Cypher.
4. Siempre devolver SOLO la consulta Cypher, sin texto adicional.
"""

# -----------------------
# Función: generar cypher
# -----------------------

async def generate_cypher(query: str, llm=None, debug: bool = False) -> str:
    """Toma una pregunta en lenguaje natural y genera un Cypher válido.
    
    Args:
        query: Pregunta en lenguaje natural
        llm: Cliente LLM (opcional, se crea uno si no se provee)
        debug: Si True, imprime debug info
    
    Returns:
        Consulta Cypher generada o "NO_CYPHER" si no se puede generar
    """
    if llm is None:
        # Log explicit reason for missing LLM to help debugging
        if GeminiClient is None:
            print("⚠️ [Text2Cypher] LLM client library 'GeminiClient' not installed or import failed.")
        elif not GEMINI_API_KEY:
            print("⚠️ [Text2Cypher] LLM API key not set: please set LLM_API_KEY in your environment.")
        else:
            print("⚠️ [Text2Cypher] LLM unavailable for unknown reason; proceeding with minimal fallbacks if applicable.")

        # Minimal, narrow rule-based fallbacks for common inventory queries
        qlow = query.lower()
        m = re.search(r"stock(?:\s+del|\s+de\s+la|\s+de)?\s+['\"]?([^\?\.'']+)", qlow)
        if m:
            prod = m.group(1).strip().strip(' "\'')
            cy = f"MATCH (p:Producto {{nombre: '{prod}'}}) RETURN p.stock AS stock LIMIT 1"
            print("⚙️ [Text2Cypher] Minimal rule-based Cypher applied (no LLM):", cy)
            return cy
        m2 = re.search(r"stock\s+mayor\s+a\s+(\d+)", qlow)
        if m2:
            n = int(m2.group(1))
            cy = f"MATCH (p:Producto) WHERE p.stock > {n} RETURN p.nombre AS nombre, p.stock AS stock LIMIT 10"
            print("⚙️ [Text2Cypher] Minimal rule-based Cypher applied (no LLM):", cy)
            return cy
        m3 = re.search(r"primeros\s+(\d+)\s+productos", qlow)
        if m3:
            lim = int(m3.group(1))
            cy = f"MATCH (p:Producto) RETURN p.nombre AS nombre, p.stock AS stock LIMIT {lim}"
            print("⚙️ [Text2Cypher] Minimal rule-based Cypher applied (no LLM):", cy)
            return cy

        return "NO_CYPHER"

    # System message: instructions, schema, rules
    system_content = (
        "Sos un agente experto en convertir preguntas de lenguaje natural a Cypher, "
        "este cypher se utilizara sobre una base de datos basada en Neo4j (grafos).\n\n"
        "Usá EXCLUSIVAMENTE el siguiente esquema de la base de datos:\n\n"
        + GRAPH_SCHEMA + "\n\n"
        "Reglas estrictas:\n"
        "- Devolver SOLO la query Cypher.\n"
        "- No explicar nada.\n"
        "- No agregar texto.\n"
        "- Si no se puede generar un Cypher válido, devolvé \"NO_CYPHER\".\n"
    )
    
    system_message = create_message(system_content, role="system")

    # User message: only the dynamic query
    user_message = create_message(
        f"Convertí la siguiente pregunta a Cypher válido: {query}",
        role="user"
    )

    if debug:
        print("\n--- Text2Cypher DEBUG: System message ---\n")
        print(system_content)
        print("\n--- Text2Cypher DEBUG: User message ---\n")
        print(f"Convertí la siguiente pregunta a Cypher válido: {query}")
        print("\n--- end prompts ---\n")

    response = await llm.generate_response([system_message, user_message])

    # Normalizar respuesta
    content = None
    if isinstance(response, dict):
        content = response.get("content")
    else:
        content = getattr(response, "content", None)

    if not content:
        return "NO_CYPHER"

    raw = content.strip()

    if debug:
        print("\n--- Text2Cypher DEBUG: raw LLM response ---\n")
        print(raw)
        print("\n--- end raw response ---\n")

    return raw

# -----------------------
# Función: ejecutar cypher en Neo4j
# -----------------------

def clean_cypher(raw: str) -> str:
    """
    Remueve backticks, bloques de código y etiquetas como ```cypher.
    """
    if raw is None:
        return ""
    
    # remover bloques ```cypher ... ```
    cleaned = re.sub(r"```[a-zA-Z]*", "", raw)  # remueve ``` y ```cypher
    cleaned = cleaned.replace("```", "")
    
    # limpiar espacios al principio y final
    cleaned = cleaned.strip()
    
    return cleaned

async def run_cypher(cypher: str, driver=None):
    """Ejecuta un Cypher en Neo4j (async).
    
    Args:
        cypher: Consulta Cypher a ejecutar
        driver: Driver de Neo4j (opcional, se crea uno si no se provee)
    
    Returns:
        Resultados de la consulta
    """
    if driver is None:
        if AsyncGraphDatabase is None or not NEO4J_URI:
            raise RuntimeError("Neo4j driver not available or NEO4J_URI not set")
        driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    async with driver.session() as session:
        result = await session.run(cypher)
        return await result.values()

# -----------------------
# Función principal del agente
# -----------------------

async def ask_graph(query: str) -> Dict[str, Any]:
    """Compatibilidad con la API existente: genera Cypher y lo ejecuta."""
    cypher = await generate_cypher(query)

    if cypher == "NO_CYPHER":
        return {"error": "No se pudo generar un Cypher válido para esta pregunta."}

    try:
        result = await run_cypher(cypher)
        return {"cypher": cypher, "results": result}
    except Exception as e:
        return {"cypher": cypher, "error": str(e)}
    
# ----------------------------------------
# FUNCIÓN PRINCIPAL
# ----------------------------------------

class Text2CypherNode:
    """Nodo que expone `async run(state: State) -> State`."""

    def __init__(self, llm: Optional[Any] = None, driver: Optional[Any] = None, model: Optional[str] = None):
        self._provided_llm = llm
        self._provided_driver = driver
        # prefer explicit model, otherwise read from env
        self.model = model or os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
    
    async def _get_llm(self) -> Any:
        """Get or create LLM client."""
        if self._provided_llm is not None:
            return self._provided_llm
        if GeminiClient is None or LLMConfig is None:
            return None
        if not GEMINI_API_KEY:
            return None
        return GeminiClient(config=LLMConfig(api_key=GEMINI_API_KEY, model=self.model))
    
    def _get_driver(self):
        """Get or create Neo4j driver."""
        if self._provided_driver is not None:
            return self._provided_driver
        if AsyncGraphDatabase is None or not NEO4J_URI:
            return None
        return AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    async def run(self, state: State) -> State:
        """Process state and generate Cypher query + results.
        
        Args:
            state: Current state with query or refined_query
            
        Returns:
            Updated state with cypher_result
        """
        # Use refined_query if available, otherwise use original query
        query = state.get("refined_query") or state.get("query", "")
        if not query:
            state["error"] = "missing 'query' in state"
            return state

        print(f"🔍 [Text2Cypher] Processing query: '{query}'")
        
        llm = await self._get_llm()
        driver = self._get_driver()

        raw_cypher = await generate_cypher(query, llm=llm)
        cypher = clean_cypher(raw_cypher)

        if cypher == "NO_CYPHER":
            # Provide explicit guidance when no Cypher could be generated
            if llm is None:
                state["cypher_result"] = {"error": "No se pudo generar un Cypher válido: LLM no configurado (ver LLM_API_KEY o instalación del cliente)."}
            else:
                state["cypher_result"] = {"error": "No se pudo generar un Cypher válido para esta pregunta."}
            return state

        # If Neo4j driver is not available, return the Cypher without executing it
        if driver is None:
            # Annotate if the Cypher was produced via minimal fallback due to missing LLM
            note_parts = ["Neo4j driver not available; cypher returned without execution."]
            if llm is None:
                note_parts.append("LLM not configured; minimal rule-based fallback may have been used.")
            state["cypher_result"] = {"cypher": cypher, "results": [], "note": " ".join(note_parts)}
            print(f"⚠️ [Text2Cypher] Neo4j driver not available; returning Cypher without execution: {cypher}")
            return state

        try:
            results = await run_cypher(cypher, driver=driver)
            state["cypher_result"] = {"cypher": cypher, "results": results}
            print(f"✅ [Text2Cypher] Query successful: {len(results)} result(s)")
        except Exception as e:
            state["cypher_result"] = {"cypher": cypher, "error": str(e)}
            print(f"❌ [Text2Cypher] Query failed: {e}")
        
        return state


async def text2cypher_node(state: State) -> State:
    """LangGraph node function for text2cypher.
    
    This is the function that will be added to the LangGraph StateGraph.
    
    Args:
        state: Current state
        
    Returns:
        Updated state with cypher_result
    """
    node = Text2CypherNode()
    return await node.run(state)


async def run_query(question: str):
    """Helper function para ejecutar una consulta directamente.
    
    Args:
        question: Pregunta en lenguaje natural
        
    Returns:
        State dict con cypher_result
    """
    node = Text2CypherNode()
    state = {"query": question, "iteration_count": 0}
    return await node.run(state)


__all__ = ["Text2CypherNode", "text2cypher_node", "run_query"]
