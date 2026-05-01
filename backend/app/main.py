from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.data_routes import router as data_router

app = FastAPI(
    title="Anomira API",
    description="AI-Powered Data Intelligence & Anomaly Detection",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "anomira-backend"}
