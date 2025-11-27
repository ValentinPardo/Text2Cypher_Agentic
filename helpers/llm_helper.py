from graphiti_core.llm_client.gemini_client import Message

def create_message(content: str, role: str = "user") -> Message:
    return Message(role=role, content=content)

