from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.adapters.retry import PermanentProviderError, TransientProviderError
from app.api import chat, documents, session

app = FastAPI(title="Chat With Your Docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(session.router)


@app.exception_handler(TransientProviderError)
async def handle_transient_provider_error(
    request: Request, exc: TransientProviderError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "A required AI service is temporarily unavailable. Please try again shortly."
        },
    )


@app.exception_handler(PermanentProviderError)
async def handle_permanent_provider_error(
    request: Request, exc: PermanentProviderError
) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "detail": "A required AI service rejected the request "
            "(check API credentials/configuration)."
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
