# CI/CD Pipeline

This project uses GitHub Actions to validate changes on pushes to `main`, then rebuild and deploy only the affected Docker Compose services.

## What the pipeline does

1. Detects which files changed in the push.
2. Maps those changes to the related Compose services.
3. Validates the Compose configuration.
4. Compiles changed Python services.
5. Starts the stack in CI and runs a smoke test.
6. Checks each service `/health` endpoint and verifies the expected OpenAPI routes exist.
7. Deploys only the changed services on the server with `docker compose up -d --build`.

## Local try-it steps

Run the stack locally from the repository root:

```bash
cd /home/uporabnik/E2EE
docker compose up -d --build
```

Then verify the main health endpoints:

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
```

To run the route smoke test directly:

```bash
python3 tests/smoke_routes.py
```

## What the smoke test checks

The repository smoke test in `tests/smoke_routes.py` checks:

- `/health` responds with `{"status": "ok"}`
- each service exposes the expected API paths in `openapi.json`
- the gateway still exposes the main request routes used by the app

## Deployment requirements

The GitHub Actions deploy job expects these secrets:

- `SERVER_HOST`
- `SERVER_USER`
- `DEPLOY_KEY`

The server must also have the repository checked out at the deploy path. The workflow currently falls back to:

```text
$HOME/E2EE
```

If your checkout is somewhere else, update the deploy path on the server or adjust the workflow.

## Notes

- The pipeline only rebuilds services affected by the change when possible.
- If `docker-compose.yml` or `init-db.sql` changes, the workflow rebuilds the full stack.
- This doc matches the current GitHub Actions workflow and smoke-test script in the repository.