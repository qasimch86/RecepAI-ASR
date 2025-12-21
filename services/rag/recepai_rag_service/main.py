from fastapi import FastAPI
from pydantic import BaseModel
from recepai_shared import settings, get_logger


app = FastAPI(title="recepai_rag_service", version="0.1.0")
logger = get_logger("recepai_rag_service")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "recepai_rag_service"}


@app.get("/info")
async def info():
    return {
        "service": "recepai_rag_service",
        "environment": settings.environment,
        "region": settings.region,
    }


class RAGQuery(BaseModel):
    query: str


@app.post("/rag/query")
async def rag_query(body: RAGQuery):
    # TODO: Replace with real RAG pipeline: retrieve -> augment -> answer.
    logger.debug("Received RAG placeholder query", extra={"len": len(body.query)})
    return {"answer": "RAG placeholder only. No vector search yet."}


if __name__ == "__main__":
    # Development runner
    import uvicorn

    uvicorn.run(
        "recepai_rag_service.main:app",
        host="0.0.0.0",
        port=5104,
        reload=True,
    )
