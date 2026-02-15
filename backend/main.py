"""
QuantumState SRE Console — FastAPI backend
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from routers import incidents, health, pipeline, chat, sim, remediate, guardian


@asynccontextmanager
async def lifespan(app: FastAPI):
    guardian.start_guardian()
    yield
    guardian.stop_guardian()


app = FastAPI(title="QuantumState SRE Console API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:3000",
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
