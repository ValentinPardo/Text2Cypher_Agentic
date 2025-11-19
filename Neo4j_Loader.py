from neo4j import GraphDatabase
from typing import Optional, Union

class Neo4jLoader:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def load_cypher(self, source: Optional[str], from_file: bool = True):
        """
        Ejecuta comandos Cypher línea por línea desde un archivo o un string.

        Parámetros:
        - source: path a archivo .cypher o string con queries
        - from_file: si True, interpreta 'source' como archivo; si False, como string

        Retorna:
            Lista con resultados de cada ejecución.
        """

        # Leer contenido
        if from_file:
            with open(source, "r", encoding="utf-8") as f:
                cypher_text = f.read()
        else:
            cypher_text = source

        # Dividir el archivo en queries separadas por ';'
        queries = [
            q.strip()
            for q in cypher_text.split(";")
            if q.strip() != ""
        ]

        results = []

        with self.driver.session() as session:
            for i, query in enumerate(queries, start=1):
                try:
                    print(f"Ejecución {i}: {query[:60]}...")
                    result = session.run(query)
                    results.append(result.consume())
                except Exception as e:
                    print(f"❌ Error en query {i}: {e}")
                    results.append(None)

        return results
