# Changelog

All notable changes to **DockView** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] — 2026-09-20

### Added

- Version badge next to the DockView name; click it to open the release notes log

## [1.1.0] — 2026-09-20

### Added

- **Open** button next to Running on containers with a published host port; opens the app in a new tab on that port

## [1.0.0] — 2026-09-20

### Added

- Container dashboard: start, stop, remove, and live status refresh
- Image list and delete (with force-delete when a container still references the image)
- Docker Hub and GitHub Container Registry catalogs with search and one-click deploy
- **Pull Latest** on running containers:
  - GitHub Compose apps: `git fetch` / latest release or codebase, then `docker compose up --build --pull always --force-recreate`
  - Local Compose apps: rebuild and recreate
  - Registry images: pull the latest tag and recreate with rollback if the new container fails to start
- Progress modal with git/pull/build logs
- Source badges (GitHub / Compose / Registry) on each container
