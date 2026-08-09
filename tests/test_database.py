from sqlalchemy import text

from remoteops.database import engine


def test_database_connection() -> None:
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1
