from fastapi import APIRouter, HTTPException

from app.db.neo4j_client import Neo4jClient

router = APIRouter()


@router.get("/health")
def health() -> dict:
    client = Neo4jClient()
    try:
        rows = client.run_read("RETURN 'ok' AS status", timeout_s=3)
        return {"api": "ok", "db": rows[0]["status"] if rows else "unknown"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Health check failed: {exc}") from exc
    finally:
        client.close()
