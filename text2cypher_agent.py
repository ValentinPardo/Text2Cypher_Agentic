import asyncio
import os
import re
from dotenv import load_dotenv

from neo4j import AsyncGraphDatabase
import google.generativeai as genai

load_dotenv(override=True)

# -------------------------
# CONFIG
# -------------------------

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS")

GEMINI_API_KEY = os.getenv("LLM_API_KEY")

SEMAPHORE_LIMIT = int(os.getenv("SEMAPHORE_LIMIT", "1"))

# Inicializar cliente global
genai.configure(api_key=GEMINI_API_KEY)

# Crear el modelo para text2cypher
llm_client = genai.GenerativeModel("gemini-2.0-flash-lite")

# Neo4j graph interface for the agent
driver = AsyncGraphDatabase.driver(
    NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
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

async def generate_cypher(query: str) -> str:
    """
    Toma una pregunta en lenguaje natural y genera un Cypher válido.
    """
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

    response = await llm_client.generate_content_async(
    [
        {
            "role": "user",
            "parts": [
                {"text": prompt}
            ]
        }
    ]
    )
    return response.text.strip()

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
    async with driver.session() as session:
        result = await session.run(cypher)
        return await result.values()

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

    raw_cypher = await generate_cypher(question)
    cypher = clean_cypher(raw_cypher)

    print(">> Cypher generado:")
    print(cypher)

    if( cypher == "NO_CYPHER"):
        print("\n>> No se pudo generar un Cypher válido para esta pregunta.")
        return {
            "error": "No se pudo generar un Cypher válido para esta pregunta."
        }
    search_results = await run_cypher(cypher)

    print("\n>> Resultado:")
    print(search_results)

    response = {
        "cypher": cypher,
        "results": search_results
    }

    return response


# ----------------------------------------
# EJEMPLO DE USO
# ----------------------------------------

if __name__ == "__main__":
    asyncio.run(run_query(
        "Mostrame los primeros 5 productos que tienen embeddings generados."
    ))
