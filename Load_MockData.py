import os
from dotenv import load_dotenv

from Neo4j_Loader import Neo4jLoader

load_dotenv(override=True)

# CONFIGURACION #
LLM_API_KEY = os.getenv("LLM_API_KEY")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASS")

print(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
print("Cargando datos de prueba en Neo4j...")

loader = Neo4jLoader(
    uri=NEO4J_URI,
    user=NEO4J_USER,
    password=NEO4J_PASS
)

loader.load_cypher("dataset.cypher", from_file=True)
loader.close()


