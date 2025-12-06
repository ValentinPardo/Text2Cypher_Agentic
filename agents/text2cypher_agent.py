# Standard imports
import asyncio
import sys
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
    import google.generativeai as genai
except Exception:
    genai = None  # type: ignore

# -------------------------
# CONFIG
# -------------------------

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS")

GEMINI_API_KEY = os.getenv("LLM_API_KEY")

# Model to use for LLM calls (set via .env to allow switching models easily)
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")

SEMAPHORE_LIMIT = int(os.getenv("SEMAPHORE_LIMIT", "1"))

# Create global clients lazily
_GLOBAL_DRIVER = None
_GLOBAL_LLM = None

def _get_driver():
    global _GLOBAL_DRIVER
    if _GLOBAL_DRIVER is not None:
        return _GLOBAL_DRIVER
    if AsyncGraphDatabase is None or not NEO4J_URI:
        return None
    _GLOBAL_DRIVER = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _GLOBAL_DRIVER

def _get_llm():
    global _GLOBAL_LLM
    if _GLOBAL_LLM is not None:
        return _GLOBAL_LLM
    if genai is None or not GEMINI_API_KEY:
        return None
    genai.configure(api_key=GEMINI_API_KEY)
    _GLOBAL_LLM = genai.GenerativeModel(LLM_MODEL)
    return _GLOBAL_LLM
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
async def generate_cypher(query: str, mock: bool = False, debug: bool = False) -> str:
    """Toma una pregunta en lenguaje natural y genera un Cypher válido.

    Basado en la versión que funcionaba previamente. Si `mock=True` devuelve un
    Cypher de ejemplo para pruebas. Construye el prompt de forma segura para
    evitar evaluación accidental de llaves en `GRAPH_SCHEMA`.
    """
        if mock:
            return "MATCH (p:Producto) RETURN p LIMIT 10"

        llm = _get_llm()
        if llm is None:
            # Log explicit reason for missing LLM to help debugging
            if genai is None:
                print("⚠️ [Text2Cypher] LLM client library 'google.generativeai' not installed or import failed.")
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

        # Build the prompt using safe concatenation to avoid evaluating braces
        prompt_intro = (
            "Sos un agente experto en convertir preguntas de lenguaje natural a Cypher, "
            "este cypher se utilizara sobre una base de datos basada en Neo4j (grafos).\n\n"
            "Usá EXCLUSIVAMENTE el siguiente esquema de la base de datos:\n\n"
        )

        prompt = prompt_intro + GRAPH_SCHEMA + "\n\n"
        prompt += (
            "Convertí la siguiente pregunta a Cypher válido:\n"
            f"PREGUNTA: \"{query}\"\n\n"
            "Reglas estrictas:\n"
            "- Devolver SOLO la query Cypher.\n"
            "- No explicar nada.\n"
            "- No agregar texto.\n"
            "- Si no se puede generar un Cypher válido, devolvé \"NO_CYPHER\".\n"
        )

        if debug:
            print("\n--- Text2Cypher DEBUG: prompt sent to LLM ---\n")
            print(prompt)
            print("\n--- end prompt ---\n")

        response = await llm.generate_content_async(
            [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ]
        )
        raw = getattr(response, "text", "").strip()
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

async def run_cypher(cypher: str):
    """Ejecuta un Cypher en Neo4j (async)."""
    driver = _get_driver()
    if driver is None:
        raise RuntimeError("Neo4j driver not available or NEO4J_URI not set")

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
    """Nodo que expone `async run(state: State) -> State`.
    """

    def __init__(self, llm: Optional[Any] = None, driver: Optional[Any] = None, model: Optional[str] = None):
        # allow overriding the model via constructor, otherwise read from env
        self.llm = llm or _get_llm()
        self.driver = driver or _get_driver()
        self.model = model or os.getenv("LLM_MODEL", LLM_MODEL)

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

        raw_cypher = await generate_cypher(query)
        cypher = clean_cypher(raw_cypher)

        if cypher == "NO_CYPHER":
            # Provide explicit guidance when no Cypher could be generated
            if self.llm is None:
                state["cypher_result"] = {"error": "No se pudo generar un Cypher válido: LLM no configurado (ver LLM_API_KEY o instalación del cliente)."}
            else:
                state["cypher_result"] = {"error": "No se pudo generar un Cypher válido para esta pregunta."}
            return state

        # If Neo4j driver is not available, return the Cypher without executing it
        if self.driver is None:
            # Annotate if the Cypher was produced via minimal fallback due to missing LLM
            note_parts = ["Neo4j driver not available; cypher returned without execution."]
            if self.llm is None:
                note_parts.append("LLM not configured; minimal rule-based fallback may have been used.")
            state["cypher_result"] = {"cypher": cypher, "results": [], "note": " ".join(note_parts)}
            print(f"⚠️ [Text2Cypher] Neo4j driver not available; returning Cypher without execution: {cypher}")
            return state

        try:
            results = await run_cypher(cypher)
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
    node = Text2CypherNode()
    state = {"query": question, "iteration_count": 0}
    return await node.run(state)


# ----------------------------------------
# EJEMPLO DE USO
# ----------------------------------------

if __name__ == "__main__":
    # Simple CLI for debugging generated Cypher.
    # Usage:
    #   python agents/text2cypher_agent.py "¿Cuál es el stock del taladro modelo X?" --debug
    args = sys.argv[1:]
    debug_flag = False
    mock_flag = False
    if "--debug" in args:
        debug_flag = True
        args = [a for a in args if a != "--debug"]
    if "--mock" in args:
        mock_flag = True
        args = [a for a in args if a != "--mock"]

    if args:
        question = " ".join(args)
    else:
        question = "Mostrame los primeros 5 productos que tienen embeddings generados."

    async def _cli():
        raw = await generate_cypher(question, mock=mock_flag, debug=debug_flag)
        cleaned = clean_cypher(raw)
        print("\n--- Text2Cypher RESULT: cleaned Cypher ---\n")
        print(cleaned)
        print("\n--- end result ---\n")

    asyncio.run(_cli())


__all__ = ["Text2CypherNode", "text2cypher_node", "run_query"]
