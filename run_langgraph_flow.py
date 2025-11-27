"""Runner interactivo para el flow definido en `flows/langgraph_flow.py`.

Uso:
  - Modo REPL (por defecto):
    python run_langgraph_flow.py
  - Modo single-shot:
    python run_langgraph_flow.py --input "Mostrar top productos" --mock
"""
import argparse
from flows.langgraph_flow import run_flow_sync


def _repl(mock: bool) -> None:
  banner = (
    "Iniciando REPL del Flow (modo mock=%s).\n"
    "Escribí tu pregunta y presioná Enter. Salir: 'salir', 'exit', 'quit' o Ctrl+C.\n"
  ) % ("ON" if mock else "OFF")
  print(banner)
  try:
    while True:
      try:
        user_input = input("\n👤 Tu pregunta (o 'salir'): ").strip()
      except EOFError:
        print("\nEOF recibido. Saliendo.")
        break

      if not user_input:
        continue
      if user_input.lower() in {"salir", "exit", "quit"}:
        print("Saliendo del REPL.")
        break

      try:
        out = run_flow_sync(user_input, mock=mock)
        print("\n--- Resultado del Flow ---")
        print(out)
      except Exception as e:
        print(f"\n⚠️  Error al ejecutar el flow: {e}")
  except KeyboardInterrupt:
    print("\nInterrupción por teclado. Saliendo.")


def main() -> None:
  parser = argparse.ArgumentParser(description="Runner para flows/langgraph_flow")
  parser.add_argument("--input", "-i", help="Consulta de usuario a ejecutar en el flow (si se omite, se inicia REPL)")
  parser.add_argument("--mock", action="store_true", help="Ejecutar en modo mock (sin LLM/BD reales)")
  args = parser.parse_args()

  if args.input:
    try:
      out = run_flow_sync(args.input, mock=args.mock)
      print("\n--- Resultado del Flow ---")
      print(out)
    except Exception as e:
      print(f"⚠️  Error al ejecutar el flow: {e}")
  else:
    _repl(mock=args.mock)


if __name__ == "__main__":
  main()
