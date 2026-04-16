# Open DORA

Open DORA is a self-hosted GitHub analytics platform that tracks engineering metrics across your organizations and repositories — commits, pull requests, code reviews, contributor stats, and more.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- A GitHub Personal Access Token (PAT) with `repo` and `read:org` scopes

## Quick Start

### 1. Create a GitHub Token

Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)** and generate a token with:
- `repo` — read access to repositories
- `read:org` — read access to organization data

### 2. Start all services

```bash
docker-compose up
```

This starts four services:

| Service  | URL                        | Description              |
|----------|----------------------------|--------------------------|
| Frontend | http://localhost:3000      | Web dashboard            |
| API      | http://localhost:8000/docs | FastAPI + Swagger UI     |
| pgAdmin  | http://localhost:5050      | Database admin (optional)|
| Postgres | localhost:5432             | Database                 |

pgAdmin credentials: `admin@admin.com` / `admin`

### 3. Open the dashboard

Navigate to http://localhost:3000 to explore your data across users, teams, repositories, and organizations.

## Project Structure

```
open-dora/
├── backend/          # FastAPI application
│   ├── app/          # API routes, models, schemas
│   ├── scripts/      # GitHub sync scripts
│   ├── migrations/   # Alembic database migrations
│   └── .env.example  # Environment variable template
├── frontend/         # Next.js dashboard
└── docker-compose.yml
```

## Stopping the stack

```bash
docker-compose down
```

To also remove stored data (database volumes):

```bash
docker-compose down -v
```

## License

[Apache 2.0](LICENSE)
