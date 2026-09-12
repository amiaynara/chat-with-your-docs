from fastapi import FastAPI

app = FastAPI(title="Chat With Your Docs")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
