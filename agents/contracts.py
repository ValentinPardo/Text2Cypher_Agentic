from pydantic import BaseModel
from typing import Optional


class RefinerInput(BaseModel):
    query: str


class RefinerOutput(BaseModel):
    refined_query: Optional[str]


class ErrorOutput(BaseModel):
    error: str
from pydantic import BaseModel
from typing import Optional


class RefineInput(BaseModel):
    query: str
    context: Optional[str] = None


class RefineOutput(BaseModel):
    refined_query: str


class ErrorOutput(BaseModel):
    error: str
