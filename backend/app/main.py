from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents

app = FastAPI(title="Chat With Your Docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
