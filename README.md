# DockView

Docker container manager with Docker Hub and GitHub Container Registry catalogs, and a **Pull Latest** action that updates a running app from GitHub or its registry image.

## Features

- List, start, stop, and remove containers
- List and delete images
- Search and deploy popular images from **Docker Hub** and **GHCR**
- **Pull Latest** on a running container:
  - **GitHub + Compose** — fetch the latest GitHub release/codebase, rebuild, and run
  - **Compose** — rebuild from the local Compose project
  - **Registry** — pull the latest image tag and recreate, keeping ports, env, and volumes

## Run

Requires Python 3.10+ and access to the host Docker daemon.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
PORT=80 ./venv/bin/gunicorn --bind 0.0.0.0:80 --workers 2 --timeout 120 app:app
```

Open [http://localhost](http://localhost) (or the port you set).

Optional `GITHUB_TOKEN` improves GHCR search/package stats and private GHCR pulls.

## Docker

DockView talks to the host Docker socket:

```bash
docker compose up --build
```

Then open [http://localhost:80](http://localhost:80).

```bash
docker compose down
```

## systemd

See [deploy/docker-dashboard.service](deploy/docker-dashboard.service) for a host install example.

See [CHANGELOG.md](CHANGELOG.md) for version history.
