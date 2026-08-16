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
ruff check remoteops tests migrations/env.py
ruff format --check remoteops tests migrations/env.py
mypy remoteops
```

## Frontend

The `frontend/` directory is a Vite + Vue 3 + TypeScript app covering the
core workflow: log in, pick or create an organization, add a project and a
contractor, log work, and approve or reject it.

```bash
cd frontend
cp .env.example .env   # VITE_API_BASE_URL, defaults to http://localhost:8000
npm install
npm run dev             # http://localhost:5173
npm run test
npm run typecheck
npm run build
```

The API must have `CORS_ALLOWED_ORIGINS=http://localhost:5173` set (see the
backend `.env.example`) or the browser will block every request.

### Known limitations

- No project/contractor/organization editing or deletion in the UI — only
  create and list, matching the roadmap's "minimal" scope for this stage.
- The access token lives in memory only and the refresh token in
  `sessionStorage` (not `localStorage`); both are lost if the tab is closed.
  This is a deliberate trade-off, not an oversight — the backend issues
  bearer tokens rather than httpOnly cookies, so this is the safer option
  available without a backend auth redesign. See the comment in
  `frontend/src/stores/auth.ts`.
- No pagination controls in the UI yet — list views show the first page
  only (the backend's pagination/filtering from Week 8 isn't surfaced here).
- No production hosting is configured. `npm run build` produces a static
  `frontend/dist/` that can be served by any static file host; there is no
  Docker service or CI job for it yet.
- Visual design is intentionally minimal — one shared stylesheet, no
  component library, one responsive breakpoint.
