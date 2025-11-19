import asyncio
from neo4j import GraphDatabase
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# -------------------------
# CONFIG
# -------------------------

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS")

GEMINI_API_KEY = os.getenv("LLM_API_KEY")

embedder = GeminiEmbedder(config=GeminiEmbedderConfig( api_key=GEMINI_API_KEY, embedding_model="gemini-embedding-001"))

EMBED_MODEL = "models/embedding-001"   # Gemini embedding model
EMBED_PROPERTY = "embedding"           # where to store the vector

# What labels to embed
TARGET_LABELS = ["Producto", "Cliente", "Compra"]   # lo que vos tengas

# Qué propiedades se combinarán como texto
SOURCE_PROPERTIES = ["name", "description"]         # modificalo según tu dataset


# -------------------------
# CONEXIÓN A NEO4J
# -------------------------

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def get_nodes_without_embedding(tx, label):
    query = f"""
    MATCH (n:{label})
    WHERE n.{EMBED_PROPERTY} IS NULL
    RETURN id(n) AS id, n AS node
    """
    return list(tx.run(query))


def update_node_embedding(tx, node_id, vector):
    query = f"""
    MATCH (n)
    WHERE id(n) = $id
    SET n.{EMBED_PROPERTY} = $vector
    """
    tx.run(query, id=node_id, vector=vector)


# -------------------------
# LOGIC
# -------------------------

async def generate_embedding(text: str):
    result = await embedder.create(
        input_data=text
    )
    return result


def build_text_from_node(node):
    parts = []
    for prop in SOURCE_PROPERTIES:
        if prop in node and node[prop]:
            parts.append(str(node[prop]))
    return " ".join(parts)


# -------------------------
# MAIN
# -------------------------

async def main():

    with driver.session() as session:

        for label in TARGET_LABELS:
            print(f"\n>>> Procesando label: {label}")

            nodes = session.execute_read(get_nodes_without_embedding, label)

            if not nodes:
                print("    No hay nodos pendientes.")
                continue

            for record in nodes:
                node_id = record["id"]
                node = record["node"]

                text = build_text_from_node(node)
                if not text.strip():
                    print(f"    Nodo {node_id} no tiene propiedades de texto, saltado.")
                    continue

                vector = await generate_embedding(text)

                session.execute_write(update_node_embedding, node_id, vector)

                print(f"    ✔ Nodo {node_id} embeddeado.")

    print("\n>>> Embeddings generados correctamente.")


if __name__ == "__main__":
    asyncio.run(main())
    print("\n🎉 Embeddings generados correctamente!")   