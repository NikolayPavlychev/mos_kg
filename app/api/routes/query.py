from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.schemas.query import (
    CypherQueryRequest,
    CypherQueryResponse,
    NLQueryRequest,
)
from app.services.agent_service import AgentService, LLMProviderError
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


@router.post("/nl", response_class=PlainTextResponse)
def query_nl(request: NLQueryRequest) -> str:
    settings = get_settings()
    agent = AgentService()
    service = QueryService()

    try:
        # Policy: provider issues should degrade to AgentService fallback whenever possible.
        # 502/504 are returned only when provider failure propagates and fallback cannot be used.
        cypher, explanation = agent.question_to_cypher(
            question=request.question,
            max_rows=settings.app_cypher_max_rows,
        )
        rows = service.run_cypher(cypher, {})
        answer = _build_nl_answer(explanation=explanation, rows=rows)
        return answer
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMProviderError as exc:
        status_code = 504 if "timeout" in str(exc).lower() else 502
        raise HTTPException(
            status_code=status_code,
            detail="LLM provider request failed and fallback was not available.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        service.close()


def _build_nl_answer(explanation: str, rows: list[dict]) -> str:
    if not rows:
        return "По вашему запросу данные не найдены."

    preview_lines: list[str] = []
    for idx, row in enumerate(rows[:5], start=1):
        if row:
            parts = [
                f"{_format_field_name(key)}: {_format_field_value(value)}"
                for key, value in row.items()
            ]
            line = "; ".join(parts)
        else:
            line = "пустая запись"
        preview_lines.append(f"{idx}) {line}")

    if len(rows) > 5:
        preview_lines.append(f"и еще {len(rows) - 5} записей.")

    preview = "\n".join(preview_lines)
    return f"Найдено записей: {len(rows)}.\n{preview}"


def _format_field_name(name: str) -> str:
    return str(name).replace("_", " ").strip()


def _format_field_value(value: object) -> str:
    if value is None:
        return "нет данных"
    return str(value)
