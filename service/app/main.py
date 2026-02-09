import asyncio
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.auth import router as auth_router
from app.api.process import router as process_router
from app.api.search import router as search_router
from app.api.chat import router as chat_router
from app.api.questions import router as questions_router
from app.api.dedup import router as dedup_router
from app.api.enrichment import router as enrichment_router
from app.telegram_bot.bot import handle_telegram_update, initialize_bot, shutdown_bot

app = FastAPI(
    title="Atlantis Plus API",
    description="AI-first Personal Network Memory",
    version="0.1.0"
)


# Lifecycle events
@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup."""
    print("[STARTUP] Initializing Telegram bot...")
    await initialize_bot()
    print("[STARTUP] Bot ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown bot on application shutdown."""
    print("[SHUTDOWN] Shutting down Telegram bot...")
    await shutdown_bot()
    print("[SHUTDOWN] Bot stopped")

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


# Telegram webhook endpoint
@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None)
):
    """
    Webhook endpoint for Telegram updates.

    Telegram sends updates here when messages arrive.
    """
    settings = get_settings()

    # Verify secret token if configured
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid secret token")

    # Parse update data
    update_data = await request.json()

    # Handle update in background (fire-and-forget for fast 200 OK)
    asyncio.create_task(handle_telegram_update(update_data))

    return {"ok": True}


# Include routers
app.include_router(auth_router)
app.include_router(process_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(questions_router)
app.include_router(dedup_router)
app.include_router(enrichment_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
