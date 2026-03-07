from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.query import (
    CypherQueryRequest,
    CypherQueryResponse,
    NLQueryRequest,
    NLQueryResponse,
)
from app.services.agent_service import AgentService
from app.services.query_service import QueryService

router = APIRouter()


@router.post("/cypher", response_model=CypherQueryResponse)
def query_cypher(request: CypherQueryRequest) -> CypherQueryResponse:
    service = QueryService()
    try:
        rows = service.run_cypher(request.query, request.params)
        return CypherQueryResponse(rows=rows, row_count=len(rows))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        service.close()


@router.post("/nl", response_model=NLQueryResponse)
def query_nl(request: NLQueryRequest) -> NLQueryResponse:
    settings = get_settings()
    agent = AgentService()
    service = QueryService()

    try:
        cypher, explanation = agent.question_to_cypher(
            question=request.question,
            max_rows=settings.app_cypher_max_rows,
        )
        rows = service.run_cypher(cypher, {})
        return NLQueryResponse(
            question=request.question,
            cypher=cypher,
            rows=rows,
            row_count=len(rows),
            explanation=explanation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        service.close()
