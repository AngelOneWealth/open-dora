# Open DORA

Open DORA is a self-hosted GitHub analytics platform that tracks engineering metrics across your organizations and repositories — commits, pull requests, code reviews, contributor stats, and more.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- A GitHub Personal Access Token (PAT) with `repo` and `read:org` scopes

## Quick Start


### 1. Start the stack

```bash
docker compose up --build
```

All four services start together. The API waits for Postgres to be healthy before booting.

| Service  | URL                        | Description              |
|----------|----------------------------|--------------------------|
| Frontend | http://localhost:3000      | Web dashboard            |
| API      | http://localhost:8000/docs | FastAPI + Swagger UI     |
| pgAdmin  | http://localhost:5050      | Database admin (optional)|
| Postgres | localhost:5432             | Database                 |

pgAdmin credentials: `admin@admin.com` / `admin`

### 2. Run database migrations

```bash
docker compose exec api alembic upgrade head
```

### 3. Open the dashboard

#### 3.1. Setup Orgs

Open the orgs page:
http://localhost:3000/orgs

Enter your org github id.
Enter the github token, process is explained below.
Add your Org.

#### 3.1. Fetch Data

After adding the org, you can either start fetching all the data or discover repos.
If you start fetching all the data, you will see the status repo by repo.

If you want to get data one by one, then 
- First Discover Repos
- Go to Repositories page in the navigation.
- Sync your data:
	- All : Get all data in one go. Sequence of data pull is Commits, PRs, Reviews, PR Commits.
	- Choose anyone from Commits, PRs, Reviews, PR Commits to do specific data fetch. We recommend doing this in the same order.

#### 3.2. Manage Users

Go to Users in the navigation or http://localhost:3000/users

- Some case you would find multiple user accounts for the same user. You can merger them by selecting multiple and click on Merge button in the top right.
- If you don't want to see sone users, you can deactivate them.
- You can create teams in the Teams section in the navigation and assign a user to a team.
- There are some git identities with no linked github account. You can found them in the "Missing Users" section in the navigation. You can link a missing user to an active user from the dropdown to merge their data.

---

## Start individual services

Start just the database
```bash
docker compose up db
```

Start the API and its dependency (db) together
```bash
docker compose up api
```

Start multiple specific services
```bash
docker compose up db api
```

Run in detached (background) mode
```bash
docker compose up -d api
```

---

## GitHub token

Generate a token at https://github.com/settings/tokens (classic). Required scopes:

| Scope | Why |
|-------|-----|
| `repo` | Read commits, PRs, and reviews for private repositories |
| `read:org` | Read organisation membership and repository lists |

---

## Useful commands

```bash
# Follow logs for a specific service
docker compose logs -f api

# Re-run migrations after pulling new code
docker compose exec api alembic upgrade head

# Sync a single repo
docker compose exec api python -m scripts.sync_github owner/repo

# Stop all services
docker compose down

# Stop and delete the database volume (fresh start)
docker compose down -v
```


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

## License

[Apache 2.0](LICENSE)
