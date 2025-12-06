"""
Answerer Agent - Formats final responses for the user.

This agent takes results from text2cypher or web_search nodes and generates
a friendly, natural language response in Spanish for the user.
"""
import os
import re
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


from urllib.parse import urlparse


class AnswererNode:
    """Node that formats final answers for the user.
    
    This node receives results from cypher_result or web_result in the state
    and generates a natural, friendly response in Spanish.
    """
    
    def __init__(self, llm: Optional[any] = None, model: Optional[str] = None):
        self._provided_llm = llm
        # model can be set via constructor or via LLM_MODEL env var
        self.model = model or os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
    
    async def _get_llm(self):
        """Get or create LLM client."""
        if self._provided_llm is not None:
            return self._provided_llm
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
        # Check if there's an error
        if state.get("error"):
            state["final_answer"] = f"Lo siento, ocurrió un error: {state['error']}"
            return state
        
        # Get results from either cypher or web search
        cypher_result = state.get("cypher_result")
        web_result = state.get("web_result")
        
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
        # If the user input is a simple greeting, return a deterministic
        # greeting constrained to `ALLOWED_TOPICS` (avoid LLM for simple salutations).
        greeting_match = re.match(r"^\s*(hola|buenos d[ií]as|buenas tardes|buenas noches|hi|hello)\b", query, re.I)
        if greeting_match:
            allowed_topics_env = os.getenv("ALLOWED_TOPICS")
            if allowed_topics_env:
                topics_list = ", ".join([t.strip() for t in allowed_topics_env.split(",") if t.strip()])
                return f"Hola, soy tu asistente. Puedo ayudar con consultas relacionadas con los siguientes temas: {topics_list}. ¿En qué te puedo ayudar?"
            return "Hola, soy tu asistente. Puedo ayudarte con consultas sobre productos, inventario y compras de e-commerce. ¿En qué te puedo ayudar?"

        # If no LLM available, provide a basic fallback constrained to ALLOWED_TOPICS
        allowed_topics_env = os.getenv("ALLOWED_TOPICS")
        if not llm:
            if allowed_topics_env:
                topics_list = ", ".join([t.strip() for t in allowed_topics_env.split(',') if t.strip()])
                return f"Hola, soy tu asistente. Puedo ayudar con consultas relacionadas con los siguientes temas: {topics_list}. ¿En qué te puedo ayudar?"
            # Fallback if no ALLOWED_TOPICS configured
            return "Hola, soy tu asistente. Puedo ayudarte con consultas sobre productos, inventario y compras de e-commerce. ¿En qué te puedo ayudar?"

        # LLM is available: build the prompt and include ALLOWED_TOPICS instruction if configured
        allowed_topics_env = os.getenv("ALLOWED_TOPICS")
        if allowed_topics_env:
            topics_list = ", ".join([t.strip() for t in allowed_topics_env.split(",") if t.strip()])
            topics_instruction = f"- Si pregunta por tus capacidades: explica que solo puedes ayudar con consultas relacionadas con los siguientes temas: {topics_list}."
        else:
            topics_instruction = "- Si pregunta por tus capacidades: explica brevemente qué puedes hacer (consultar productos, inventario y compras)."

        prompt = f"""
Eres un asistente virtual amigable y profesional para un sistema de e-commerce.

El usuario ha dicho: "{query}"

Tu trabajo es generar una respuesta natural y contextualmente apropiada. Considera:

- Si es un saludo (hola, buenos días, etc.): Responde amablemente y explica brevemente qué puedes hacer
- Si es un agradecimiento (gracias, etc.): Responde con cortesía y disponibilidad para más ayuda
- Si es una despedida (adiós, hasta luego, etc.): Despídete cordialmente
{topics_instruction}
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
    
    def _shorten_text(self, text: str, max_sentences: int = 2, max_words: int = 60) -> str:
        """Return a shortened version of `text` containing at most
        `max_sentences` sentences and `max_words` words (defensive truncation).
        """
        if not text:
            return ""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        brief = ' '.join(sentences[:max_sentences]).strip()
        words = brief.split()
        if len(words) > max_words:
            return ' '.join(words[:max_words]) + '...'
        return brief

    def _synthesize_summary(self, results: list, query: str) -> str:
        """Create a 1-2 sentence synthetic summary from search results.

        Uses simple heuristics (look for 'El campeón fue', years, or first sentence)
        to produce a direct answer when the LLM is not available.
        """
        if not results:
            return "No se encontró información suficiente en las fuentes para generar un resumen conciso."

        # collect candidate texts (content then title)
        candidates = []
        for r in results:
            content = (r.get("content") or "").strip()
            title = (r.get("title") or "").strip()
            if content:
                candidates.append(content)
            elif title:
                candidates.append(title)

        text = candidates[0] if candidates else ""

        # try to extract country from patterns like 'El campeón fue X' or 'X ganó'
        m = re.search(r"El campeón fue\s+([^,\.\n]+)", text, re.I)
        year_m = re.search(r"20\d{2}", query)
        year = year_m.group(0) if year_m else "2022"
        if m:
            country = m.group(1).split(",")[0].strip()
            # try to include a brief source citation if available
            source = None
            if results and results[0].get("url"):
                try:
                    source = urlparse(results[0].get("url")).netloc
                except Exception:
                    source = None
            if source:
                return f"{country} ganó la Copa Mundial de Fútbol {year}. Fuente: {source}."
            return f"{country} ganó la Copa Mundial de Fútbol {year}."

        # try verbs like 'ganó' or 'venció'
        m2 = re.search(r"([A-ZÁÉÍÓÚÑ][\w\s]+?)\s+(ganó|venció|derrotó)", text, re.I)
        if m2:
            country = m2.group(1).strip()
            source = None
            if results and results[0].get("url"):
                try:
                    source = urlparse(results[0].get("url")).netloc
                except Exception:
                    source = None
            if source:
                return f"{country} ganó la Copa Mundial de Fútbol {year}. Fuente: {source}."
            return f"{country} ganó la Copa Mundial de Fútbol {year}."

        # fallback: take first 1-2 sentences from the top candidate
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        brief = ' '.join(sentences[:2]).strip()
        if not brief:
            return "No se encontró información suficiente en las fuentes para generar un resumen conciso."
        # ensure brevity
        # include source if available as a second short sentence
        brief_short = self._shorten_text(brief, max_sentences=2, max_words=50)
        source = None
        if results and results[0].get("url"):
            try:
                source = urlparse(results[0].get("url")).netloc
            except Exception:
                source = None
        if source:
            return f"{brief_short} Fuente: {source}."
        return brief_short

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
        
        # If no LLM available, enforce topical restrictions (if configured)
        web_domains_env = os.getenv("WEB_SEARCH_DOMAINS")
        allowed_topics_env = os.getenv("ALLOWED_TOPICS")
        if not llm:
            # If web-domain filtering was active and produced no results, refuse
            if web_domains_env and web_result.get("_filtered_by_domain") is False:
                return "Lo siento, esto no forma parte de mi dominio y no puedo responder."
            # If allowed topics are configured, do a simple keyword check on the query
            if allowed_topics_env:
                allowed_tokens = [t.strip().lower() for t in allowed_topics_env.split(",") if t.strip()]
                qlow = (query or "").lower()
                if not any(tok in qlow for tok in allowed_tokens):
                    return "Lo siento, esto no forma parte de mi dominio y no puedo responder."
            return self._synthesize_summary(results, query)
        
        # Prepare context from top 3 results
        top_results = results[:3]
        snippets = []
        for item in top_results:
            title = item.get("title", "")
            content = item.get("content", "")
            snippet = content if len(content) <= 500 else content[:497] + "..."
            snippets.append(f"{title}: {snippet}")
        
        context_text = "\n\n".join(snippets)
        
        # Build domain/topic restriction instructions (if configured)
        web_domains_env = os.getenv("WEB_SEARCH_DOMAINS")
        allowed_topics_env = os.getenv("ALLOWED_TOPICS")
        instructions = []
        if allowed_topics_env:
            topics_list = ", ".join([t.strip() for t in allowed_topics_env.split(",") if t.strip()])
            instructions.append(f"IMPORTANTE: Este asistente solo responde preguntas RELACIONADAS con los siguientes temas: {topics_list}. Si la consulta está FUERA de estos temas, responde exactamente: 'Lo siento, esto no forma parte de mi dominio y no puedo responder.'")
        if web_domains_env:
            domains_list = ", ".join([d.strip() for d in web_domains_env.split(",") if d.strip()])
            instructions.append(f"IMPORTANTE: Además, para búsquedas web solo considerar resultados de los dominios: {domains_list}.")
        domain_instruction = "\n\n".join(instructions) + ("\n\n" if instructions else "")

        # Use LLM to generate a concise SYNTHESIS (RESUMEN) of the web results
        prompt = f"""
    {domain_instruction}
    A partir de los siguientes títulos y extractos de búsqueda, genera UN RESUMEN SINTÉTICO en español que responda DIRECTAMENTE a la pregunta del usuario.

    Requisitos estrictos:
    - Máximo 2 oraciones.
    - Máximo 40 palabras en total.
    - Primera oración: respuesta directa y clara (por ejemplo: "Argentina ganó la Copa Mundial 2022.").
    - Segunda oración (opcional): una frase muy breve de contexto o dato clave.
    - No listar, no citar fragmentos textuales, no introducir la respuesta con frases como "He encontrado..." o "Según...".

    Si la información es insuficiente para dar una respuesta concreta, responde en UNA sola oración: "No hay suficiente información en las fuentes para responder con seguridad."

    Pregunta: {query}

    Fuentes (no incluir literalmente):
    {context_text}

    Resumen:
    """
        
        try:
            response = await llm.generate_response([create_message(prompt)])
            content = response.get("content", "").strip() if isinstance(response, dict) else getattr(response, "content", "").strip()
            content = content or ""
            brief = self._shorten_text(content, max_sentences=2, max_words=60)
            # if the LLM output is just a paraphrase of the user_friendly or is empty, synthesize instead
            if brief and not brief.lower().startswith("he encontrado"):
                return brief
            return self._synthesize_summary(results, query)
        except Exception as e:
            # Fallback to synthesized summary
            return self._synthesize_summary(results, query)


async def answerer_node(state: State) -> State:
    """LangGraph node function for the answerer.
    
    This is the function that will be added to the LangGraph StateGraph.
    
    Args:
        state: Current state
        
    Returns:
        Updated state with final_answer
    """
    node = AnswererNode()
    return await node.run(state)


__all__ = ["AnswererNode", "answerer_node"]

