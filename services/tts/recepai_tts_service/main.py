from fastapi import FastAPI
from pydantic import BaseModel
from recepai_shared import settings, get_logger


app = FastAPI(title="recepai_tts_service", version="0.1.0")
logger = get_logger("recepai_tts_service")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "recepai_tts_service"}


@app.get("/info")
async def info():
    return {
        "service": "recepai_tts_service",
        "environment": settings.environment,
        "region": settings.region,
    }


class TTSRequest(BaseModel):
    text: str


@app.post("/tts/dummy")
async def tts_dummy(body: TTSRequest):
    # TODO: Replace with real TTS synthesis logic in later phases.
    logger.debug("Received TTS placeholder request", extra={"len": len(body.text)})
    return {"message": "TTS placeholder only. No audio generated yet."}


if __name__ == "__main__":
    # Development runner
    import uvicorn

    uvicorn.run(
        "recepai_tts_service.main:app",
        host="0.0.0.0",
        port=5103,
        reload=True,
    )
