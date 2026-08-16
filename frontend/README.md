# RemoteOps frontend

Vue 3 + TypeScript + Pinia + Vue Router frontend for the RemoteOps API,
covering the core workflow: log in → pick/create an organization → add a
project and a contractor → log work → approve or reject it.

## Setup

```bash
cp .env.example .env   # set VITE_API_BASE_URL if the API isn't on localhost:8000
npm install
npm run dev
```

The backend must allow this origin via `CORS_ALLOWED_ORIGINS` (see the
repository root README).

## Commands

```bash
npm run dev         # start the Vite dev server
npm run test         # run Vitest once
npm run typecheck    # vue-tsc, no emit
npm run build         # production build to dist/
npm run preview       # serve the production build locally
```

## Structure

```
src/api/          typed fetch client + one module per backend resource
src/stores/auth.ts Pinia auth store (login/logout/session restore)
src/router/        routes + auth guard
src/composables/   useAsyncResource: shared loading/error/retry state
src/views/         LoginView, DashboardView, OrganizationView
```

See the repository root README's "Frontend" section for known limitations.
