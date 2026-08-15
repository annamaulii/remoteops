from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from remoteops.audit import router as audit_router
from remoteops.documents import router as documents_router
from remoteops.config import settings
from remoteops.database import engine
from remoteops.organizations import router as organizations_router
from remoteops.reliability import configure_reliability
from remoteops.resources import router as resources_router
from remoteops.users import router as users_router
from remoteops.workflows import router as workflows_router

app = FastAPI(title="RemoteOps", version="0.1.0")
configure_reliability(
    app, settings.auth_rate_limit, settings.auth_rate_window_seconds
)
app.include_router(audit_router)
app.include_router(documents_router)
app.include_router(organizations_router)
app.include_router(resources_router)
app.include_router(users_router)
app.include_router(workflows_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def check_database() -> None:
    """Verify that PostgreSQL accepts a minimal query."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


@app.get("/ready")
def ready() -> dict[str, str]:
    """Report whether this process can serve database-backed traffic."""
    try:
        check_database()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Service unavailable") from None
    return {"status": "ready"}
