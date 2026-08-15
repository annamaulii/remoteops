from fastapi import FastAPI

from remoteops.audit import router as audit_router
from remoteops.documents import router as documents_router
from remoteops.organizations import router as organizations_router
from remoteops.resources import router as resources_router
from remoteops.users import router as users_router
from remoteops.workflows import router as workflows_router

app = FastAPI(title="RemoteOps", version="0.1.0")
app.include_router(audit_router)
app.include_router(documents_router)
app.include_router(organizations_router)
app.include_router(resources_router)
app.include_router(users_router)
app.include_router(workflows_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
