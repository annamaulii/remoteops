from fastapi import FastAPI

from remoteops.organizations import router as organizations_router

app = FastAPI(title="RemoteOps", version="0.1.0")
app.include_router(organizations_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
