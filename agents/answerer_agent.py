"""
Answerer Agent - Formats final responses for the user.

This agent takes results from text2cypher or web_search nodes and generates
a friendly, natural language response in Spanish for the user.
"""
import os
from typing import Optional
from dotenv import load_dotenv

from agents.contracts import State

load_dotenv(override=True)

# Optional import of LLM client
try:
    from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
    from helpers.llm_helper import create_message
    _LLM_AVAILABLE = True
except Exception:
    _LLM_AVAILABLE = False

GEMINI_API_KEY = os.getenv("LLM_API_KEY")


class AnswererNode:
    """Node that formats final answers for the user.
    
    This node receives results from cypher_result or web_result in the state
    and generates a natural, friendly response in Spanish.
    """
    
    def __init__(self, llm: Optional[any] = None, model: str = "gemini-2.0-flash-lite", mock: bool = False):
        self._provided_llm = llm
        self.model = model
        self.mock = mock
    
    async def _get_llm(self):
        """Get or create LLM client."""
        if self._provided_llm is not None:
            return self._provided_llm
        if self.mock:
            return None
        if not _LLM_AVAILABLE or not GEMINI_API_KEY:
            return None
        return GeminiClient(config=LLMConfig(api_key=GEMINI_API_KEY, model=self.model))
    
    
    async def run(self, state: State) -> State:
        """Process the state and generate a final answer.
        
        Args:
            state: Current state with query and results
            
        Returns:
            Updated state with final_answer field populated
        """
        query = state.get("query", "")
        mock = state.get("mock", self.mock)
        
        # Check if there's an error
        if state.get("error"):
            state["final_answer"] = f"Lo siento, ocurrió un error: {state['error']}"
            return state
        
        # Get results from either cypher or web search
        cypher_result = state.get("cypher_result")
        web_result = state.get("web_result")
        
        # If mock mode, return a simple mock response
        if mock:
            if cypher_result:
                state["final_answer"] = f"(MOCK) Respuesta basada en consulta a base de datos para: {query}"
            elif web_result:
                state["final_answer"] = f"(MOCK) Respuesta basada en búsqueda web para: {query}"
            else:
                state["final_answer"] = f"(MOCK) Respuesta conversacional para: {query}"
            return state
        
        # Format cypher results
        if cypher_result:
            final_answer = await self._format_cypher_response(query, cypher_result)
            state["final_answer"] = final_answer
            return state
        
        # Format web search results
        if web_result:
            final_answer = await self._format_web_response(query, web_result)
            state["final_answer"] = final_answer
            return state
        
        # No results but we still need to answer (conversational query)
        # Use LLM to generate an intelligent contextual response
        final_answer = await self._format_conversational_response(query)
        state["final_answer"] = final_answer
        return state
    
    async def _format_cypher_response(self, query: str, cypher_result: dict) -> str:
        """Format cypher query results into a natural language response."""
        llm = await self._get_llm()
        
        # Check if there was an error in cypher execution
        if cypher_result.get("error"):
            return f"No pude ejecutar la consulta en la base de datos: {cypher_result['error']}"
        
        results = cypher_result.get("results", [])
        cypher_query = cypher_result.get("cypher", "")
        
        # If no LLM available, return a simple formatted response
        if not llm:
            if not results:
                return "No se encontraron resultados en la base de datos para tu consulta."
            return f"Encontré {len(results)} resultado(s) en la base de datos. Resultados: {str(results)[:500]}"
        
        # Use LLM to format a natural response
        prompt = f"""
Eres un asistente experto en e-commerce. Un usuario hizo la siguiente pregunta:
"{query}"

Se ejecutó una consulta Cypher en la base de datos Neo4j:
{cypher_query}

Resultados obtenidos:
{results}

Por favor, genera una respuesta natural, clara y concisa en español para el usuario.
- Si no hay resultados, informa amablemente que no se encontró información.
- Si hay resultados, preséntelos de manera organizada y fácil de entender.
- No menciones términos técnicos como "Cypher" o "Neo4j" al usuario.
- Sé breve pero informativo.

Respuesta:
"""
        
        try:
            response = await llm.generate_response([create_message(prompt)])
            content = response.get("content", "").strip() if isinstance(response, dict) else getattr(response, "content", "").strip()
            return content if content else "Procesé tu consulta pero no pude generar una respuesta adecuada."
        except Exception as e:
            # Fallback if LLM fails
            if not results:
                return "No se encontraron resultados en la base de datos."
            return f"Encontré {len(results)} resultado(s): {str(results)[:300]}..."
    
    async def _format_conversational_response(self, query: str) -> str:
        """Generate an intelligent response for conversational queries using LLM.
        
        This handles greetings, thanks, goodbyes, help requests, and other
        conversational interactions without predefined responses.
        """
        llm = await self._get_llm()
        
        # If no LLM available, provide a basic fallback
        if not llm:
            return "Hola, soy tu asistente. Puedo ayudarte con consultas sobre nuestra base de datos de e-commerce o búsquedas web. ¿En qué te puedo ayudar?"
        
        prompt = f"""
Eres un asistente virtual amigable y profesional para un sistema de e-commerce.

El usuario ha dicho: "{query}"

Tu trabajo es generar una respuesta natural y contextualmente apropiada. Considera:

- Si es un saludo (hola, buenos días, etc.): Responde amablemente y explica brevemente qué puedes hacer
- Si es un agradecimiento (gracias, etc.): Responde con cortesía y disponibilidad para más ayuda
- Si es una despedida (adiós, hasta luego, etc.): Despídete cordialmente
- Si pregunta por tus capacidades (qué puedes hacer, ayuda, etc.): Explica que puedes:
  * Consultar la base de datos de e-commerce (productos, clientes, compras, inventario)
  * Realizar búsquedas web para información general
  * Entender y responder preguntas en lenguaje natural
- Para cualquier otra consulta conversacional: Responde de manera natural y útil

IMPORTANTE:
- Mantén un tono amigable pero profesional
- Sé conciso pero informativo
- Responde en español
- No inventes información técnica o datos

Respuesta:
"""
        
        try:
            response = await llm.generate_response([create_message(prompt)])
            content = response.get("content", "").strip() if isinstance(response, dict) else getattr(response, "content", "").strip()
            return content if content else "¿En qué puedo ayudarte hoy?"
        except Exception as e:
            # Fallback if LLM fails
            return "Hola, soy tu asistente. Puedo ayudarte con consultas sobre e-commerce o búsquedas web. ¿Qué necesitas?"
    
    async def _format_web_response(self, query: str, web_result: dict) -> str:
        """Format web search results into a natural language response."""
        llm = await self._get_llm()
        
        # Check if web search had an error
        if not web_result.get("success"):
            error_msg = web_result.get("error", "Error desconocido")
            return f"No pude realizar la búsqueda web: {error_msg}"
        
        results = web_result.get("results", [])
        
        # If no results found
        if not results:
            return f"No encontré información relevante en la web sobre '{query}'."
        
        # If no LLM available, return the user_friendly field or a simple response
        if not llm:
            return web_result.get("user_friendly", f"Encontré {len(results)} resultados en la web para tu consulta.")
        
        # Prepare context from top 3 results
        top_results = results[:3]
        snippets = []
        for item in top_results:
            title = item.get("title", "")
            content = item.get("content", "")
            snippet = content if len(content) <= 500 else content[:497] + "..."
            snippets.append(f"{title}: {snippet}")
        
        context_text = "\n\n".join(snippets)
        
        # Use LLM to generate a comprehensive answer
        prompt = f"""
Usando los siguientes resultados de búsqueda web como contexto, responde la pregunta del usuario de manera clara y concisa en español:

Pregunta del usuario: {query}

Contexto de búsqueda web:
{context_text}

Instrucciones:
- Genera una respuesta natural y directa basada en la información disponible.
- Si la información es suficiente, responde con confianza.
- Si no hay suficiente información, indícalo claramente.
- No menciones "según los resultados de búsqueda" - presenta la información como si la supieras.
- Sé breve pero completo.

Respuesta:
"""
        
        try:
            response = await llm.generate_response([create_message(prompt)])
            content = response.get("content", "").strip() if isinstance(response, dict) else getattr(response, "content", "").strip()
            return content if content else web_result.get("user_friendly", f"Encontré información sobre tu consulta pero no pude procesarla adecuadamente.")
        except Exception as e:
            # Fallback to user_friendly field
            return web_result.get("user_friendly", f"Encontré {len(results)} resultados relevantes en la web.")


async def answerer_node(state: State) -> State:
    """LangGraph node function for the answerer.
    
    This is the function that will be added to the LangGraph StateGraph.
    
    Args:
        state: Current state
        
    Returns:
        Updated state with final_answer
    """
    node = AnswererNode(mock=state.get("mock", False))
    return await node.run(state)


__all__ = ["AnswererNode", "answerer_node"]

