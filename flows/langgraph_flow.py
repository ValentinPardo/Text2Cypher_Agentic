"""
Flow runner que construye un flujo minimal usando el `Orchestrator` existente.

Este archivo proporciona una capa de entrada simple para ejecutar el flujo completo
usando los nodos reescritos (`RefinerNode`, `WebSearchNode`, `Text2CypherNode`).

Actualmente el `Orchestrator` ya implementa la lógica de decisión y llamadas a
los nodos; este módulo actúa como punto de integración y como lugar para añadir
adaptadores de estado si se desea en el futuro.
"""
import asyncio
from typing import Any

from agents.orchestrator_agent import Orchestrator


async def run_flow(user_input: str, mock: bool = True) -> Any:
    """Ejecuta el flujo completo sobre `user_input`.

    - `mock=True` forzará nodos a usar sus modos mock cuando correspondan.
    - Devuelve el resultado final que produce el orquestador (puede ser dict o str).
    """
    orchestrator = Orchestrator()
    # Forzar modo mock si se solicita
    orchestrator.use_mock_by_default = bool(mock)
    result = await orchestrator.orchestrate(user_input)
    return result


def run_flow_sync(user_input: str, mock: bool = True) -> Any:
    return asyncio.run(run_flow(user_input, mock=mock))


__all__ = ["run_flow", "run_flow_sync"]
