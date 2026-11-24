"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.config import configure_langsmith, settings
from app.graph import close_compiled_graph, get_compiled_graph


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize application resources and release them during shutdown."""
    application.state.settings = settings

    configure_langsmith(settings)

    try:
        application.state.procurement_graph = await get_compiled_graph()
        yield
    finally:
        application.state.procurement_graph = None
        await close_compiled_graph()


app = FastAPI(
    title="AI-Powered Procurement and Vendor Assistant",
    description="Policy-aware procurement workflows with LangGraph, RAG, MCP, and human approval.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(api_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    """Return basic service metadata."""
    return {
        "name": "AI-Powered Procurement and Vendor Assistant",
        "status": "running",
    }


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Report whether the API process is healthy."""
    return {"status": "ok"}