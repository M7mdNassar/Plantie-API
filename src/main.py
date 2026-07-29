# src/main.py
"""App entrypoint.

The single most important change vs the old version: every expensive object
(the local embedding model, the Supabase client, the LLM SDK client, the
Retriever/DatabaseService/ChatAgent that wrap them) is built exactly ONCE,
here, in `lifespan`, and stored on `app.state`. Routes pull the already-built
instances via dependency functions instead of constructing their own on
every request.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client

from src.api.middleware.logging import logging_middleware
from src.api.routes import chat, health
from src.config import get_settings
from src.core.agent.chat import ChatAgent
from src.core.rag.embedder import Embedder
from src.core.rag.retriever import Retriever
from src.services.supabase.database import DatabaseService
from src.utils.logging import get_logger, setup_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger = get_logger()
    logger.info("Starting up: loading embedding model and building shared clients...")

    supabase_client = create_client(
        settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
    )
    embedder = Embedder()  # loads the local ONNX model once, here — not per request
    retriever = Retriever(embedder=embedder, client=supabase_client)
    db = DatabaseService(client=supabase_client)
    chat_agent = ChatAgent(retriever=retriever, db=db)

    app.state.supabase = supabase_client
    app.state.embedder = embedder
    app.state.retriever = retriever
    app.state.db = db
    app.state.chat_agent = chat_agent

    logger.info("Startup complete — ready to serve requests.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered agricultural assistant",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: replace with an explicit allow-list before shipping
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth is now handled per-route via Depends(get_current_user) — see
# src/api/dependencies/auth.py — so it isn't a global middleware anymore.
app.middleware("http")(logging_middleware)

app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])

# The unauthenticated test endpoint only exists when DEBUG=true, so it can
# never be reachable in a real deployment.
if settings.DEBUG:
    from src.api.routes import test_chat

    app.include_router(test_chat.router, prefix="/api/v1/test", tags=["Test Chat"])


@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "status": "healthy"}