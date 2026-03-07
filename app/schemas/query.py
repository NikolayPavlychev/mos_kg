from pydantic import BaseModel, Field


class CypherQueryRequest(BaseModel):
    query: str = Field(..., description="Raw Cypher query to execute")
    params: dict = Field(default_factory=dict)


class CypherQueryResponse(BaseModel):
    rows: list[dict]
    row_count: int


class NLQueryRequest(BaseModel):
    question: str = Field(..., min_length=2)


class NLQueryResponse(BaseModel):
    question: str
    cypher: str
    rows: list[dict]
    row_count: int
    explanation: str
