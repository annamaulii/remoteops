# RemoteOps

Backend-first platform for managing distributed teams and contractors.

## Run with Docker

Create a private environment file and replace its placeholder secrets:

```bash
install -m 600 .env.example .env
openssl rand -hex 32
docker compose up --build
```

Use the generated value for both PostgreSQL password placeholders in `.env`,
then generate separate values for the JWT and webhook signing secrets.

The API is available at <http://127.0.0.1:8000/docs>. PostgreSQL stays on
`127.0.0.1:5432`; migrations run before the API and webhook worker start.

```bash
docker compose logs -f api webhook-worker
docker compose down
```

`docker compose down` preserves PostgreSQL data. Use `docker compose down -v`
only when you intentionally want to delete the database volume and its data.

## Rollback

The `migrate` service runs `alembic upgrade head` automatically on every
`docker compose up`. To undo the most recent migration:

```bash
docker compose run --rm migrate alembic downgrade -1
```

Then restart the API so it picks up the reverted schema:

```bash
docker compose restart api
```

Rolling back a migration does not restore data dropped by that migration's
`upgrade()` step; it only reverses the schema change. Restore the `postgres_data`
volume from a backup if you need the data back too.

## Local development

```bash
python -m pip install -e ".[dev]"
docker compose up -d postgres
alembic upgrade head
pytest
```
