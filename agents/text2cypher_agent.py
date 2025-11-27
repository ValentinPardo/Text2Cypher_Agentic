# Standard imports
import asyncio
import os
import re
from dotenv import load_dotenv
from typing import Any, Dict, Optional

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
    _GLOBAL_LLM = genai.GenerativeModel("gemini-2.0-flash-lite")
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
# Función: generar cypher
# -----------------------

async def generate_cypher(query: str, mock: bool = False) -> str:
    """Toma una pregunta en lenguaje natural y genera un Cypher válido.

    Si `mock=True` retorna un Cypher de prueba sin llamar al LLM.
    """
    if mock:
        # Un cypher de ejemplo seguro para pruebas
        return "MATCH (p:Producto) RETURN p LIMIT 10"

    llm = _get_llm()
    if llm is None:
        # No hay LLM disponible en el entorno; devolver NO_CYPHER para evitar falsos positivos
        return "NO_CYPHER"

    prompt = f"""
Sos un agente experto en convertir preguntas de lenguaje natural a Cypher, este cypher se utilizara sobre una base de datos basada en Neo4j (grafos).
Usá EXCLUSIVAMENTE el siguiente esquema de la base de datos:

{GRAPH_SCHEMA}

Convertí la siguiente pregunta a Cypher válido:
PREGUNTA: "{query}"

Reglas estrictas:
- Devolver SOLO la query Cypher.
- No explicar nada.
- No agregar texto.
- Si no se puede generar un Cypher válido, devolvé "NO_CYPHER".
"""

    response = await llm.generate_content_async(
        [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ]
    )
    return getattr(response, "text", "").strip()

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

async def run_cypher(cypher: str, mock: bool = False):
    """Ejecuta un Cypher en Neo4j (async). Si `mock=True` devuelve datos de ejemplo."""
    if mock:
        return [[{"mock": True, "cypher": cypher}]]

    driver = _get_driver()
    if driver is None:
        raise RuntimeError("Neo4j driver not available or NEO4J_URI not set")

    async with driver.session() as session:
        result = await session.run(cypher)
        return await result.values()

# -----------------------
# Función principal del agente
# -----------------------

async def ask_graph(query: str, mock: bool = False) -> Dict[str, Any]:
    """Compatibilidad con la API existente: genera Cypher y lo ejecuta.

    `mock=True` evita llamadas reales a LLM y BD.
    """
    cypher = await generate_cypher(query, mock=mock)

    if cypher == "NO_CYPHER":
        return {"error": "No se pudo generar un Cypher válido para esta pregunta."}

    try:
        result = await run_cypher(cypher, mock=mock)
        return {"cypher": cypher, "results": result}
    except Exception as e:
        return {"cypher": cypher, "error": str(e)}
    
# ----------------------------------------
# FUNCIÓN PRINCIPAL
# ----------------------------------------

class Text2CypherNode:
    """Nodo que expone `async run(inputs: dict) -> dict`.

    Inputs esperados: {"query": str, "mock": bool (optional)}
    Output: {"cypher": str, "results": ...} o {"error": str}
    """

    def __init__(self, llm: Optional[Any] = None, driver: Optional[Any] = None, model: str = "gemini-2.0-flash-lite", mock: bool = False):
        self.llm = llm or _get_llm()
        self.driver = driver or _get_driver()
        self.model = model
        self.mock = mock

    async def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        query = inputs.get("query") or inputs.get("question")
        if not query:
            return {"error": "missing 'query' in inputs"}

        mock = bool(inputs.get("mock", self.mock))

        raw_cypher = await generate_cypher(query, mock=mock)
        cypher = clean_cypher(raw_cypher)

        if cypher == "NO_CYPHER":
            return {"error": "No se pudo generar un Cypher válido para esta pregunta."}

        try:
            results = await run_cypher(cypher, mock=mock)
            return {"cypher": cypher, "results": results}
        except Exception as e:
            return {"cypher": cypher, "error": str(e)}


async def run_query(question: str, mock: bool = False):
    node = Text2CypherNode(mock=mock)
    return await node.run({"query": question, "mock": mock})


# ----------------------------------------
# EJEMPLO DE USO
# ----------------------------------------

if __name__ == "__main__":
    asyncio.run(run_query(
        "Mostrame los primeros 5 productos que tienen embeddings generados."
    ))
