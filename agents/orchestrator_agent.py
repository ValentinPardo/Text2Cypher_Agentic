"""
Orchestrator Agent - Routes queries to appropriate agents.

This agent analyzes the user query and decides which agent should handle it:
- answerer: Simple greetings or direct responses
- refiner: Ambiguous queries that need refinement
- text_to_cypher: Database queries about e-commerce data
- web_search: General knowledge questions requiring web search
"""
import asyncio
import os
from typing import Literal
from dotenv import load_dotenv

from agents.contracts import State

load_dotenv(override=True)

try:
    from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
    from helpers.llm_helper import create_message
    _LLM_AVAILABLE = True
except Exception:
    _LLM_AVAILABLE = False


class OrchestratorNode:
    """Orchestrator that decides routing for incoming queries."""
    
    def __init__(self, llm_api_key: str = None):
        self.llm_api_key = llm_api_key or os.getenv("LLM_API_KEY")
    
    
    async def decide_route(self, query: str, refined_query: str = None, iteration_count: int = 0) -> str:
        """Decide which agent should handle the query.
        
        Returns one of: "answerer", "refiner", "text_to_cypher", "web_search"
        """
        # Prevent infinite loops - if we've refined too many times, go to text_to_cypher or web_search
        if iteration_count >= 2:
            # Make a final decision without refining again
            if self._seems_db_query(refined_query or query):
                return "text_to_cypher"
            return "web_search"
        
        # Use the refined query if available for decision making
        query_to_analyze = refined_query if refined_query else query
        
        # If no LLM or missing API key, use heuristics
        if not _LLM_AVAILABLE or not self.llm_api_key:
            return self._heuristic_route(query_to_analyze)
        
        # Use LLM for decision
        try:
            model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
            client = GeminiClient(config=LLMConfig(api_key=self.llm_api_key, model=model_name))
            
            prompt = f"""
Eres un orquestador experto que clasifica consultas de usuario para un sistema de e-commerce.

Analiza la siguiente consulta y decide la mejor ruta:

Consulta: "{query_to_analyze}"

Opciones disponibles:

1. **ANSWERER** - Para interacciones conversacionales directas:
   - Saludos, despedidas, agradecimientos
   - Preguntas sobre capacidades del sistema ("qué puedes hacer", "ayuda")
   - Consultas muy simples que no requieren búsqueda de datos
   
2. **TEXT_TO_CYPHER** - Para consultas sobre datos de e-commerce:
   - Información sobre productos, clientes, compras, inventario, comunidades
   - Análisis de ventas, estadísticas del negocio
   - Cualquier pregunta que requiera consultar la base de datos interna
   
3. **WEB_SEARCH** - Para información externa:
   - Eventos actuales, noticias
   - Definiciones generales, conocimiento externo
   - Información que NO está en la base de datos de e-commerce
   
4. **REFINER** - Si la consulta necesita clarificación:
   - Consultas ambiguas o vagas
   - Preguntas incompletas
   - Consultas que necesitan más contexto antes de procesarse

IMPORTANTE: Usa tu inteligencia para determinar la intención real del usuario. No te bases solo en palabras clave.

Devuelve SOLO UNA PALABRA: ANSWERER, TEXT_TO_CYPHER, WEB_SEARCH, o REFINER
"""
            
            response = await client.generate_response([create_message(prompt)])
            decision = response.get("content", "").strip().upper() if isinstance(response, dict) else ""
            
            # Map decision to route
            if "TEXT_TO_CYPHER" in decision or "CYPHER" in decision:
                return "text_to_cypher"
            if "WEB_SEARCH" in decision or "WEB" in decision:
                return "web_search"
            if "REFINER" in decision or "REFINE" in decision:
                return "refiner"
            if "ANSWERER" in decision or "ANSWER" in decision:
                return "answerer"
            
            # Default fallback
            return self._heuristic_route(query_to_analyze)
            
        except Exception as e:
            print(f"⚠️  [Orchestrator] LLM decision failed: {e}, using heuristics")
            return self._heuristic_route(query_to_analyze)
    
    def _heuristic_route(self, query: str) -> str:
        """Use simple heuristics to route the query when LLM is not available.
        
        This is a fallback when LLM is not available. It's intentionally simple
        and conservative. When LLM is available, it should be used instead for
        more intelligent routing.
        """
        query_lower = query.lower()
        
        # Very short queries (1-2 words) that look conversational
        words = query.strip().split()
        if len(words) <= 2:
            # Check if it seems conversational
            conversational_words = ["hola", "hi", "hello", "gracias", "thanks", "adiós", "bye", "ayuda", "help"]
            if any(word in query_lower for word in conversational_words):
                return "answerer"
        
        # Check for database-related keywords
        db_keywords = [
            "producto", "productos", "cliente", "clientes", "compra", "compras",
            "venta", "ventas", "stock", "inventario", "pedido", "pedidos",
            "comunidad", "comunidades", "precio", "precios", "top", "mejor",
            "mayor", "menor", "total", "cantidad", "cuanto", "cuantos"
        ]
        
        if any(keyword in query_lower for keyword in db_keywords):
            # If query is too vague, refine it first
            if self._is_vague_query(query):
                return "refiner"
            return "text_to_cypher"
        
        # Check if query is vague/ambiguous
        if self._is_vague_query(query):
            return "refiner"
        
        # Default to web search for general questions
        return "web_search"
    
    def _is_vague_query(self, query: str) -> bool:
        """Check if query is too vague and needs refinement."""
        vague_indicators = [
            len(query.split()) <= 3,  # Very short queries
            query.strip().endswith("?") and len(query.split()) <= 4,  # Very short questions
        ]
        
        # If it's very short but has clear db keywords, it's not vague
        if len(query.split()) <= 3 and self._seems_db_query(query):
            return False
        
        return any(vague_indicators)
    
    def _seems_db_query(self, query: str) -> bool:
        """Check if query seems to be about database data."""
        db_keywords = [
            "producto", "productos", "cliente", "clientes", "compra", "compras",
            "venta", "ventas", "stock", "inventario", "pedido", "pedidos",
            "comunidad", "comunidades", "precio", "precios"
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in db_keywords)
    
    async def run(self, state: State) -> State:
        """Process state and make routing decision.
        
        Args:
            state: Current state with query
            
        Returns:
            Updated state with route_decision field
        """
        query = state.get("query", "")
        refined_query = state.get("refined_query")
        iteration_count = state.get("iteration_count", 0)

        print(f"\n🤖 [Orchestrator] Analyzing: '{query}' (iteration={iteration_count})")
        if refined_query:
            print(f"   Refined version: '{refined_query}'")
        
        # Make routing decision
        route = await self.decide_route(query, refined_query, iteration_count)

        # Enforce allowed-topic gating early: if the decision would send the
        # query to the DB (`text_to_cypher`) but the query does not contain any
        # of the configured `ALLOWED_TOPICS`, treat it as out-of-domain and
        # route to `web_search` instead. This prevents sending unrelated
        # questions to the DB node before we even try a Cypher generation.
        allowed_topics_env = os.getenv("ALLOWED_TOPICS", "").strip()
        if route == "text_to_cypher" and allowed_topics_env:
            allowed_tokens = [t.strip().lower() for t in allowed_topics_env.split(",") if t.strip()]
            q_to_check = (refined_query or query or "").lower()
            if not any(tok in q_to_check for tok in allowed_tokens):
                print("⚠️  [Orchestrator] Query appears outside ALLOWED_TOPICS; re-routing to web_search.")
                state.setdefault("route_annotations", {})["domain_check"] = {
                    "allowed_topics": allowed_tokens,
                    "matched": False,
                    "note": "Rerouted from text_to_cypher to web_search because query did not match allowed topics.",
                }
                route = "web_search"
        
        print(f"🔀 [Orchestrator] Decision: {route}")
        
        # Update state with decision
        state["route_decision"] = route
        
        return state


async def orchestrator_node(state: State) -> State:
    """LangGraph node function for orchestrator.
    
    This is the function that will be added to the LangGraph StateGraph.
    
    Args:
        state: Current state
        
    Returns:
        Updated state with route_decision
    """
    orchestrator = OrchestratorNode()
    return await orchestrator.run(state)


def route_decision(state: State) -> Literal["refiner", "text_to_cypher", "web_search", "answerer"]:
    """Routing function for conditional edges in LangGraph.
    
    This function determines which node to visit next based on the orchestrator's decision.
    
    Args:
        state: Current state with route_decision field
        
    Returns:
        Name of the next node to visit
    """
    decision = state.get("route_decision", "text_to_cypher")
    print(f"🔀 [Router] Routing to: {decision}")
    return decision


__all__ = ["OrchestratorNode", "orchestrator_node", "route_decision"]
