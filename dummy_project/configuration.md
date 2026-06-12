# Configuration

The application is configured entirely through environment variables.
All settings have sensible defaults for local development.

## Environment Variables

### Application Settings

| Variable | Default | Description |
|---|---|---|
| `APP_HOST` | `0.0.0.0` | Host address the server binds to |
| `APP_PORT` | `8000` | Port the server listens on |
| `DEBUG` | `false` | Enable debug mode |
| `TOKEN_EXPIRY` | `3600` | Auth token lifetime in seconds |
| `RATE_LIMIT` | `60` | Max requests per minute per user |

### Database Settings

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `userdb` | Database name |
| `DB_USER` | `postgres` | Database username |
| `DB_PASSWORD` | _(empty)_ | Database password |

## Loading Config

Call `load_config` once at application startup:

```python
from src.config import load_config

config = load_config()
print(config.db.url)  # postgresql://postgres:@localhost:5432/userdb
```

## DatabaseConfig

The `DatabaseConfig` class holds database connection settings.
Access the full connection URL via the `url` property:

```python
config = load_config()
db_url = config.db.url
```

## AppConfig

The `AppConfig` class holds all top-level settings. Key fields:

- `debug` — bool, whether debug mode is on
- `host` — server bind address
- `port` — server port (default 8000)
- `token_expiry_seconds` — how long tokens stay valid
- `max_requests_per_minute` — rate limit threshold
- `db` — a nested `DatabaseConfig` instance
