from fastapi import FastAPI

from app.routes.scans import router as scans_router

app = FastAPI(title="pyscanapi-agent")

app.include_router(scans_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
