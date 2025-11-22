import os
from dotenv import load_dotenv
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig

## Importar el helper para crear mensajes
from helpers.llm_helper import create_message

load_dotenv(override=True)

# -------------------------
# CONFIG
# -------------------------

GEMINI_API_KEY = os.getenv("LLM_API_KEY")

# Gemini LLM for Refiner
# Using a capable model for reasoning
llm_client = GeminiClient(config=LLMConfig(api_key=GEMINI_API_KEY, model="gemini-2.0-flash-lite"))

async def refine_query(user_query: str) -> str:
    """
    Takes a natural language query and rewrites it to be more explicit and structured 
    for the database agent (Text2Cypher).
    """
    prompt = f"""
    Sos un agente experto en "Refinamiento de Consultas".
    Tu objetivo es tomar una pregunta de un usuario (que puede ser vaga, ambigua o informal)
    y reescribirla para que sea:
    1. Clara y explícita.
    2. Fácil de entender para un agente que genera código Cypher (Neo4j).
    3. Manteniendo la intención original del usuario.

    Si la pregunta ya es clara, devolvela tal cual o con mínimas mejoras.
    Si la pregunta es muy ambigua, tratá de inferir lo más probable o hacela más específica basándote en un contexto de e-commerce (Productos, Clientes, Compras, Comunidades).

    EJEMPLOS:
    Input: "cuales son los top productos"
    Output: "Listar los 5 productos con mayor cantidad de ventas."

    Input: "que cliente compro mas"
    Output: "Identificar al cliente que ha realizado el mayor gasto total en compras."

    Input: "{user_query}"
    Output:
    """

    response = await llm_client.generate_response([create_message(prompt)])
    refined_query = response['content'].strip()
    
    return refined_query

if __name__ == "__main__":
    import asyncio
    async def main():
        q = "dame lo que mas se vende"
        print(f"Original: {q}")
        refined = await refine_query(q)
        print(f"Refined: {refined}")

    asyncio.run(main())
