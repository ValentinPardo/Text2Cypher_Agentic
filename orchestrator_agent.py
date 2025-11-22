import asyncio
import os
from dotenv import load_dotenv
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig, Message

# Importar los otros agentes
from agents.refiner_agent import refine_query
from agents.text2cypher_agent import ask_graph
from agents.web_search_agent import web_search

# Importar el helper para crear mensajes
from helpers.llm_helper import create_message

load_dotenv(override=True)

# -------------------------
# CONFIG
# -------------------------

GEMINI_API_KEY = os.getenv("LLM_API_KEY")

# Gemini LLM for Orchestrator
llm_client = GeminiClient(config=LLMConfig(api_key=GEMINI_API_KEY, model="gemini-2.0-flash-lite"))

async def decide_route(user_input: str) -> str:
    """
    Decide qué acción tomar basándose en el input del usuario.
    Retorna: 'REFINE', 'QUERY_DB', 'ANSWER'
    """

    prompt = f"""
    Sos el ORQUESTADOR de un sistema de agentes. 
    Tu trabajo es recibir un input del usuario y decidir a qué agente enviarlo.

    Tus opciones son:
    1. REFINE: El usuario está haciendo una pregunta sobre la base de datos (productos, clientes, compras, comunidades), pero la pregunta podría ser ambigua, informal o compleja. Necesita pasar por el Refiner Agent para mejorarla antes de consultar la DB.
       Ejemplos: "dame lo mas vendido", "quien compro mas", "top productos", "ventas de ayer".
    
    2. QUERY_DB: El usuario está haciendo una pregunta sobre la base de datos que YA es muy clara, precisa y estructurada. Puede ir directo al Text2Cypher Agent.
       Ejemplos: "Listar los 5 productos con mayor stock", "Mostrar el total de compras del cliente Juan Perez".
       (Nota: Ante la duda, preferí REFINE para asegurar calidad).

    4. WEB_SEARCH: El usuario está pidiendo información que probablemente no esté en la base de datos, o es de carácter general o actual. Necesita realizar una búsqueda web primero para obtener contexto.
       Ejemplos: "¿Cuáles son las últimas tendencias en tecnología para 2025?", "¿Qué opinan los expertos sobre el cambio climático este año?", "Noticias recientes sobre inteligencia artificial".

    3. ANSWER: El usuario está saludando, agradeciendo, o preguntando algo fuera del contexto de la base de datos. Vos podés responder directamente.
       Ejemplos: "Hola", "Gracias", "Como estas?", "Que podes hacer?".

    Input del usuario: "{user_input}"

    Respuesta (SOLO una palabra): REFINE, QUERY_DB, ANSWER o WEB_SEARCH
    """

    response = await llm_client.generate_response([create_message(prompt)])
    print(response)
    ## limpia los posibles espacios y saltos de linea
    decision = response['content'].strip().upper()
    
    # Limpieza básica por si el modelo devuelve algo extra
    if "REFINE" in decision: return "REFINE"
    if "QUERY_DB" in decision: return "QUERY_DB"
    if "WEB_SEARCH" in decision: return "WEB_SEARCH"
    if "ANSWER" in decision: return "ANSWER"
    
    return "ANSWER" # Default

async def orchestrate(user_input: str):
    print(f"\n🤖 [Orchestrator] Recibido: '{user_input}'")
    
    route = await decide_route(user_input)
    print(f"🔀 [Orchestrator] Decisión: {route}")

    if route == "ANSWER":
        # Responder directamente (puedes usar el mismo LLM para generar una respuesta amable)
        prompt = f"El usuario dijo: '{user_input}'. Respondé amablemente como un asistente de base de datos. Sé breve."
        response = await llm_client.generate_response([create_message(prompt)])
        print(f"💬 [Orchestrator]: {response['content'].strip()}")
        return response['content'].strip()

    elif route == "REFINE":
        print("   -> Enviando a Refiner Agent...")
        refined_query = await refine_query(user_input)
        print(f"✨ [Refiner] Consulta refinada: '{refined_query}'")
        
        # Una vez refinada, la mandamos a la DB (Text2Cypher)
        print("   -> Enviando a Text2Cypher Agent...")
        result = await ask_graph(refined_query)
        
        # Mostrar resultado
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return f"Error: {result['error']}"
        else:
            print(f"📊 [Text2Cypher] Resultados encontrados: {len(result['results'])}")
            # Aquí podrías formatear los resultados con el LLM si quisieras, pero por ahora devolvemos raw
            return result

    elif route == "QUERY_DB":
        print("   -> Enviando directo a Text2Cypher Agent...")
        result = await ask_graph(user_input)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return f"Error: {result['error']}"
        else:
            print(f"📊 [Text2Cypher] Resultados encontrados: {len(result['results'])}")
            return result
        
    elif route == "WEB_SEARCH":
        print("   -> Realizando búsqueda web (Tavily)...")
        # use_mock True si no hay clave configurada
        use_mock = not bool(os.getenv("TAVILY_API_KEY"))
        # Llamamos a la versión async de web_search
        web_result = await web_search(user_input, max_results=3, use_mock=use_mock)
        if not web_result.get("success"):
            print(f"⚠️  [WebSearch] Falló la búsqueda: {web_result.get('error')}")
            # Fallback: enviar directamente a refiner sin contexto
            refined_query = await refine_query(user_input)
        else:
            # Tomar los top snippets y agregarlos como contexto minimal
            top = web_result.get("results", [])[:3]
            context_snippets = []
            for r in top:
                title = r.get("title", "")
                content = r.get("content", "")
                # limitar la longitud para evitar prompts enormes
                snippet = content if len(content) <= 500 else content[:497] + "..."
                context_snippets.append(f"{title}: {snippet}")

            context_text = "\n".join(context_snippets)
            user_with_context = f"{user_input}\n\nContexto (web):\n{context_text}"

            print(f"   -> [WebSearch] Top {len(top)} resultados añadidos como contexto.")
            # Enviamos a Refiner para mejorar la consulta con contexto
            refined_query = await refine_query(user_with_context)

        print(f"✨ [Refiner] Consulta refinada (desde WebSearch): '{refined_query}'")
        print("   -> Enviando a Text2Cypher Agent...")
        result = await ask_graph(refined_query)

        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return f"Error: {result['error']}"
        else:
            print(f"📊 [Text2Cypher] Resultados encontrados: {len(result['results'])}")
            return result
# ----------------------------------------
# EJEMPLO DE USO
# ----------------------------------------

if __name__ == "__main__":
    async def main():
        while True:
            user_input = input("\n👤 Tu pregunta (o 'salir'): ")
            if user_input.lower() in ["salir", "exit"]:
                break
            await orchestrate(user_input)

    asyncio.run(main())
