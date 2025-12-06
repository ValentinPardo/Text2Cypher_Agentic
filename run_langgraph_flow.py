"""Runner interactivo para el flow definido en `flows/langgraph_flow.py`.

Uso:
  - Modo REPL (por defecto):
    python run_langgraph_flow.py
  - Modo single-shot:
    python run_langgraph_flow.py --input "Mostrar top productos" --mock
"""
import argparse
from dotenv import load_dotenv

load_dotenv(override=True)


async def _repl_async(mock: bool) -> None:
    """Async REPL that maintains the event loop for all queries."""
    banner = (
        "Iniciando REPL del Flow (modo mock=%s).\n"
        "Escribí tu pregunta y presioná Enter. Salir: 'salir', 'exit', 'quit' o Ctrl+C.\n"
    ) % ("ON" if mock else "OFF")
    print(banner)
    
    from flows.langgraph_flow import run_flow_async
    
    try:
        while True:
            try:
                # Use asyncio to handle input in async context
                import sys
                sys.stdout.write("\n👤 Tu pregunta (o 'salir'): ")
                sys.stdout.flush()
                user_input = sys.stdin.readline().strip()
            except EOFError:
                print("\nEOF recibido. Saliendo.")
                break

            if not user_input:
                continue
            if user_input.lower() in {"salir", "exit", "quit"}:
                print("Saliendo del REPL.")
                break

            try:
                # Execute the flow and get final state (async)
                final_state = await run_flow_async(user_input, mock=mock)
                
                # Display the final answer
                print("\n--- Respuesta Final ---")
                final_answer = final_state.get("final_answer")
                if final_answer:
                    print(final_answer)
                else:
                    print("No se pudo generar una respuesta.")
                
                # Optionally show additional debug info
                if final_state.get("error"):
                    print(f"\n⚠️  Error: {final_state['error']}")
                    
            except Exception as e:
                print(f"\n⚠️  Error al ejecutar el flow: {e}")
                import traceback
                traceback.print_exc()
    except KeyboardInterrupt:
        print("\nInterrupción por teclado. Saliendo.")


def _repl(mock: bool) -> None:
    """Wrapper to run async REPL in a persistent event loop."""
    import asyncio
    asyncio.run(_repl_async(mock))


async def _main_async(args) -> None:
    """Async main function for single-shot queries."""
    from flows.langgraph_flow import run_flow_async
    
    try:
        # Execute the flow and get final state
        final_state = await run_flow_async(args.input, mock=args.mock)
        
        # Display the final answer
        print("\n--- Respuesta Final ---")
        final_answer = final_state.get("final_answer")
        if final_answer:
            print(final_answer)
        else:
            print("No se pudo generar una respuesta.")
        
        # Show debug info if requested
        if args.debug:
            print("\n--- Estado Completo (Debug) ---")
            for key, value in final_state.items():
                if key != "final_answer":  # Already displayed
                    print(f"{key}: {value}")
        
        # Show errors if any
        if final_state.get("error"):
            print(f"\n⚠️  Error: {final_state['error']}")
            
    except Exception as e:
        print(f"⚠️  Error al ejecutar el flow: {e}")
        import traceback
        traceback.print_exc()


def main() -> None:
    import asyncio
    
    parser = argparse.ArgumentParser(description="Runner para flows/langgraph_flow")
    parser.add_argument("--input", "-i", help="Consulta de usuario a ejecutar en el flow (si se omite, se inicia REPL)")
    parser.add_argument("--mock", action="store_true", help="Ejecutar en modo mock (sin LLM/BD reales)")
    parser.add_argument("--debug", action="store_true", help="Mostrar información de debug completa")
    args = parser.parse_args()

    if args.input:
        asyncio.run(_main_async(args))
    else:
        _repl(mock=args.mock)


if __name__ == "__main__":
    main()
