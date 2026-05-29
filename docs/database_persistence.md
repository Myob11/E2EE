# Database Persistence in E2EE

This document explains how database persistence is implemented in the E2EE app and how to reproduce the same pattern in another Docker Compose project.

## What actually makes data persist

Persistence is achieved by combining three things:

1. Named Docker volumes store the real database files outside the container filesystem.
2. Database containers mount those volumes at the correct internal data paths.
3. The startup and shutdown scripts avoid deleting volumes, so containers can be stopped and recreated without losing data.

The result is:

- PostgreSQL data survives `./start.sh` and `./stop.sh`
- MongoDB data survives `./start.sh` and `./stop.sh`
- Schema initialization happens only on first boot or when missing objects need to be recreated

## Docker Compose storage wiring

The persistence layer is defined in `docker-compose.yml`.

### PostgreSQL

```yaml
postgres:
  image: postgres:15-alpine
  container_name: e2ee_postgres
  environment:
    - "POSTGRES_USER=${POSTGRES_USER:-postgres}"
    - POSTGRES_PASSWORD=postgres
    - POSTGRES_DB=auth_db
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro
```

What each line does:

- `postgres_data:/var/lib/postgresql/data` stores PostgreSQL's data directory in a named volume.
- `./init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro` mounts the schema bootstrap SQL into the official PostgreSQL init directory.
- `POSTGRES_DB=auth_db` tells the container to create and use `auth_db` on first initialization.

### MongoDB

```yaml
mongodb:
  image: mongo:7
  container_name: e2ee_mongodb
  environment:
    - MONGO_INITDB_DATABASE=messages_db
    - "MONGO_INITDB_ROOT_USERNAME=${MONGO_USER:-admin}"
    - "MONGO_INITDB_ROOT_PASSWORD=${MONGO_PASSWORD:?Error: MONGO_PASSWORD not set}"
  volumes:
    - mongodb_data:/data/db
```

What each line does:

- `mongodb_data:/data/db` stores MongoDB's database files in a named volume.
- `MONGO_INITDB_DATABASE` sets the initial database name.
- The root username/password are injected from environment variables so the container can initialize securely.

### Named volumes

```yaml
volumes:
  postgres_data:
  mongodb_data:
```

This declares the persistent storage as Docker-managed named volumes rather than bind mounts. Docker keeps these volumes even if the containers are recreated.

## Schema bootstrap for PostgreSQL

The file `init-db.sql` contains the first-run schema creation:

```sql
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

This works because PostgreSQL only runs files in `/docker-entrypoint-initdb.d/` when the data directory is empty. After the named volume already contains data, the init script is skipped and existing tables remain intact.

## Startup script behavior

The `start.sh` script does not wipe storage. It starts PostgreSQL first, waits for it to become healthy, then starts the rest of the application.

```bash
echo "Starting PostgreSQL first..."
sudo "${COMPOSE_CMD[@]}" up -d postgres

echo "Waiting for PostgreSQL to become healthy..."
for i in {1..60}; do
	if sudo "${COMPOSE_CMD[@]}" exec -T postgres pg_isready -U "${POSTGRES_USER:-postgres}" >/dev/null 2>&1; then
		echo "✅ PostgreSQL is ready"
		break
	fi
	sleep 2
done

echo "Verifying auth_db schema..."
sudo "${COMPOSE_CMD[@]}" exec -T postgres psql -U "${POSTGRES_USER:-postgres}" -d auth_db -c "\\dt" 2>/dev/null || {
	echo "⚠️  Schema not found, letting init script create it..."
}

echo "Starting remaining services (MongoDB, MinIO, API Gateway, services)..."
sudo "${COMPOSE_CMD[@]}" up -d
```

What this does:

- Brings up the database before the app services.
- Uses `pg_isready` so the script waits for a live PostgreSQL connection.
- Checks whether `auth_db` already has tables.
- Starts the rest of the stack only after the database is ready.

The important persistence detail is that `start.sh` does not recreate the volumes. It only recreates containers if needed.

## Shutdown script behavior

The `stop.sh` script preserves volumes explicitly:

```bash
# Stop containers WITHOUT removing volumes
${SUDO} "${COMPOSE_CMD[@]}" stop
```

This is the critical difference between stopping containers and deleting storage:

- `docker compose stop` stops containers only.
- `docker compose down` removes containers and the network, but keeps named volumes.
- `docker compose down -v` deletes named volumes and wipes data.

For this app, the normal stop path avoids `-v`, so data remains on disk in the named volumes.

## Application-side database setup

The auth service also initializes its schema on startup.

```python
@app.on_event("startup")
def on_startup():
    setup_database()
```

Inside `setup_database()`, the service uses `CREATE TABLE IF NOT EXISTS` and `CREATE SEQUENCE IF NOT EXISTS`.

```python
cur.execute("CREATE SEQUENCE IF NOT EXISTS user_id_seq;")
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id text PRIMARY KEY,
        username text UNIQUE NOT NULL,
        password text NOT NULL,
        public_key text,
        registration_id int
    )
    """
)
```

This means the app can restart safely:

- If the database already exists, it reuses the data in the volume.
- If a table is missing, the service creates it without dropping existing data.

## Replicable recipe

To reproduce this pattern in another project, follow these steps:

1. Add a named volume for each database.
2. Mount the database's real data directory into that named volume.
3. Mount an init SQL file into the official database init directory if the database supports it.
4. Start the database container first.
5. Wait for readiness before starting application services.
6. Make schema creation idempotent with `IF NOT EXISTS`.
7. Stop containers with `docker compose stop` or `docker compose down`, not `docker compose down -v`.

## Short version

If you want the one-sentence explanation: the app persists database state by keeping PostgreSQL and MongoDB data in named Docker volumes, bootstrapping schema only on first initialization, and using start/stop scripts that never delete those volumes during normal restarts.