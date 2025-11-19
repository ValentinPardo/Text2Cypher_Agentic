import asyncio
import os
from dotenv import load_dotenv
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
from graphiti_core.driver.neo4j_driver import Neo4jDriver

load_dotenv(override=True)

# -------------------------
# CONFIG
# -------------------------

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS")

GEMINI_API_KEY = os.getenv("LLM_API_KEY")

# Gemini LLM
llm_client = GeminiClient(config=LLMConfig(api_key=GEMINI_API_KEY,model="gemini-2.0-flash-lite"))

# Neo4j graph interface for the agent
graph = Neo4jDriver(
    uri=NEO4J_URI,
    user=NEO4J_USER,
    password=NEO4J_PASSWORD,
    database="neo4j"
    )

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
(:Producto)-[:INVENTARIA]->(:Comunidad)

REGLAS:
1. No inventes propiedades ni relaciones.
2. Si no se puede responder con los datos existentes, devolvé "NO_CYPHER".
3. No acepto múltiples consultas Cypher.
4. Siempre devolver SOLO la consulta Cypher, sin texto adicional.
"""

# -----------------------
# Función: generar cypher
# -----------------------

async def generate_cypher(query: str) -> str:
    """
    Toma una pregunta en lenguaje natural y genera un Cypher válido.
    """
    prompt = f"""
Sos un agente experto en convertir preguntas a Cypher.
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

    response = await llm_client.generate_response(prompt)
    cypher = response.text.strip()

    # Evitar multílinea con explicaciones
    if "match" not in cypher.lower():
        return "NO_CYPHER"

    return cypher

# -----------------------
# Función: ejecutar cypher en Neo4j
# -----------------------

driver = Neo4jDriver(
    uri=NEO4J_URI,
    user=NEO4J_USER,
    password=NEO4J_PASSWORD,
    database="neo4j"
)

def run_cypher(cypher: str):
    """
    Ejecuta la consulta cypher y devuelve los resultados.
    """
    with driver.session() as session:
        result = session.run(cypher)
        return [r.data() for r in result]


# -----------------------
# Función principal del agente
# -----------------------

async def ask_graph(query: str):
    cypher = await generate_cypher(query)

    if cypher == "NO_CYPHER":
        return {"error": "No se pudo generar un Cypher válido para esta pregunta."}

    try:
        result = run_cypher(cypher)
        return {
            "cypher": cypher,
            "results": result
        }
    except Exception as e:
        return {
            "cypher": cypher,
            "error": str(e)
        }
    
# ----------------------------------------
# FUNCIÓN PRINCIPAL
# ----------------------------------------

async def run_query(question: str):
    print("\n-------------------------------")
    print("Pregunta:", question)
    print("-------------------------------\n")

    response = await generate_cypher(question)

    print(">> Cypher generado:")
    print(response.cypher)
    print("\n>> Resultado:")
    print(response.data)

    return response


# ----------------------------------------
# EJEMPLO DE USO
# ----------------------------------------

if __name__ == "__main__":
    asyncio.run(run_query(
        "Mostrame los 5 productos más vendidos y sus cantidades."
    ))
