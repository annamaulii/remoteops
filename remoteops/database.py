from sqlalchemy import create_engine

from remoteops.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
