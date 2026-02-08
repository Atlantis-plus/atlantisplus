from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.auth import router as auth_router
from app.api.process import router as process_router
from app.api.search import router as search_router

app = FastAPI(
    title="Atlantis Plus API",
    description="AI-first Personal Network Memory",
    version="0.1.0"
)

# CORS for Telegram Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mini App can run from various domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "version": "0.1.0"
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Atlantis Plus API",
        "docs": "/docs"
    }


# Include routers
app.include_router(auth_router)
app.include_router(process_router)
app.include_router(search_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
