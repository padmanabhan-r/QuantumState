"""
QuantumState SRE Console — FastAPI backend
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from creds import set_creds

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from routers import incidents, health, pipeline, chat, sim, remediate, guardian


@asynccontextmanager
async def lifespan(app: FastAPI):
    guardian.start_guardian()
    yield
    guardian.stop_guardian()


app = FastAPI(title="QuantumState SRE Console API", version="2.0.0", lifespan=lifespan)


@app.middleware("http")
async def credential_override_middleware(request: Request, call_next):
    """Read per-request credential headers and store in ContextVar.
    Falls back to server env vars if headers are absent."""
    creds = {k: v for k, v in {
        "cloud_id":  request.headers.get("X-Elastic-Cloud-Id"),
        "api_key":   request.headers.get("X-Elastic-Api-Key"),
        "kibana_url": request.headers.get("X-Kibana-Url"),
    }.items() if v}
    set_creds(creds)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:3000",
        "https://quantumstate.online",
        "https://www.quantumstate.online",
        "https://quantum-state-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents.router, prefix="/api")
app.include_router(health.router,    prefix="/api")
app.include_router(pipeline.router,  prefix="/api")
app.include_router(chat.router,      prefix="/api")
app.include_router(sim.router,       prefix="/api")
app.include_router(remediate.router, prefix="/api")
app.include_router(guardian.router,  prefix="/api")


@app.get("/api/ping")
def ping():
    return {"status": "ok"}
