#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone

import docker
import requests
from docker.errors import APIError, ImageNotFound, NotFound
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
client = docker.from_env()

HUB_API = "https://hub.docker.com/v2"
GITHUB_API = "https://api.github.com"
REGISTRY_TIMEOUT = 10
JOBS_DIR = os.environ.get("DOCKVIEW_JOBS_DIR", "/tmp/dockview-jobs")
PULL_TIMEOUT = int(os.environ.get("DOCKVIEW_PULL_TIMEOUT", "1200"))
COMPOSE_LABEL_WORKDIR = "com.docker.compose.project.working_dir"
COMPOSE_LABEL_CONFIG = "com.docker.compose.project.config_files"
COMPOSE_LABEL_SERVICE = "com.docker.compose.service"
COMPOSE_LABEL_PROJECT = "com.docker.compose.project"

REGISTRY_DOCKER_HUB = "docker-hub"
REGISTRY_GHCR = "ghcr"

REGISTRIES = {
    REGISTRY_DOCKER_HUB: {
        "id": REGISTRY_DOCKER_HUB,
        "name": "Docker Hub",
        "short_name": "Docker Hub",
        "search_placeholder": "Search Docker Hub repos...",
    },
    REGISTRY_GHCR: {
        "id": REGISTRY_GHCR,
        "name": "GitHub Container Registry",
        "short_name": "GHCR",
        "search_placeholder": "Search GHCR packages...",
    },
}

POPULAR_REPOS = [
    {
        "id": "nginx",
        "name": "NGINX",
        "image": "nginx:latest",
        "namespace": "library",
        "hub_name": "nginx",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/nginx",
        "description": "High-performance web server and reverse proxy.",
        "container_port": 80,
        "default_host_port": 8080,
        "icon": "🌐",
        "logo_domain": "nginx.org",
    },
    {
        "id": "redis",
        "name": "Redis",
        "image": "redis:latest",
        "namespace": "library",
        "hub_name": "redis",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/redis",
        "description": "In-memory cache, vector search, and data store.",
        "container_port": 6379,
        "default_host_port": 6379,
        "icon": "⚡",
        "logo_domain": "redis.io",
    },
    {
        "id": "postgres",
        "name": "PostgreSQL",
        "image": "postgres:latest",
        "namespace": "library",
        "hub_name": "postgres",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/postgres",
        "description": "Powerful open-source relational database.",
        "container_port": 5432,
        "default_host_port": 5432,
        "icon": "🐘",
        "logo_domain": "postgresql.org",
        "env_defaults": {"POSTGRES_PASSWORD": "postgres"},
    },
    {
        "id": "mysql",
        "name": "MySQL",
        "image": "mysql:latest",
        "namespace": "library",
        "hub_name": "mysql",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/mysql",
        "description": "Popular open-source relational database server.",
        "container_port": 3306,
        "default_host_port": 3306,
        "icon": "🐬",
        "logo_domain": "mysql.com",
        "env_defaults": {"MYSQL_ROOT_PASSWORD": "mysql"},
    },
    {
        "id": "mongo",
        "name": "MongoDB",
        "image": "mongo:latest",
        "namespace": "library",
        "hub_name": "mongo",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/mongo",
        "description": "Document-oriented NoSQL database.",
        "container_port": 27017,
        "default_host_port": 27017,
        "icon": "🍃",
        "logo_domain": "mongodb.com",
    },
    {
        "id": "httpd",
        "name": "Apache HTTPD",
        "image": "httpd:latest",
        "namespace": "library",
        "hub_name": "httpd",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/httpd",
        "description": "Apache HTTP Server for serving web content.",
        "container_port": 80,
        "default_host_port": 8080,
        "icon": "🪶",
        "logo_domain": "apache.org",
    },
    {
        "id": "node",
        "name": "Node.js",
        "image": "node:latest",
        "namespace": "library",
        "hub_name": "node",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/node",
        "description": "JavaScript runtime built on Chrome's V8 engine.",
        "container_port": 3000,
        "default_host_port": 3000,
        "icon": "🟢",
        "logo_domain": "nodejs.org",
    },
    {
        "id": "python",
        "name": "Python",
        "image": "python:latest",
        "namespace": "library",
        "hub_name": "python",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/python",
        "description": "Official Python language runtime image.",
        "container_port": 8000,
        "default_host_port": 8000,
        "icon": "🐍",
        "logo_domain": "python.org",
    },
    {
        "id": "ubuntu",
        "name": "Ubuntu",
        "image": "ubuntu:latest",
        "namespace": "library",
        "hub_name": "ubuntu",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/ubuntu",
        "description": "Ubuntu base image for building and running applications.",
        "icon": "🟠",
        "logo_domain": "ubuntu.com",
    },
    {
        "id": "alpine",
        "name": "Alpine",
        "image": "alpine:latest",
        "namespace": "library",
        "hub_name": "alpine",
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": "https://hub.docker.com/_/alpine",
        "description": "Minimal Docker image based on Alpine Linux.",
        "icon": "🏔️",
        "logo_domain": "alpinelinux.org",
    },
]

POPULAR_GHCR_REPOS = [
    {
        "id": "ghcr-home-assistant",
        "name": "Home Assistant",
        "image": "ghcr.io/home-assistant/home-assistant:stable",
        "namespace": "home-assistant",
        "hub_name": "home-assistant",
        "github_owner": "home-assistant",
        "github_package": "home-assistant",
        "github_repo": "home-assistant/core",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/home-assistant/core/pkgs/container/home-assistant",
        "description": "Open-source home automation platform.",
        "container_port": 8123,
        "default_host_port": 8123,
        "icon": "🏠",
        "logo_domain": "home-assistant.io",
    },
    {
        "id": "ghcr-traefik",
        "name": "Traefik",
        "image": "ghcr.io/traefik/traefik:latest",
        "namespace": "traefik",
        "hub_name": "traefik",
        "github_owner": "traefik",
        "github_package": "traefik",
        "github_repo": "traefik/traefik",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/traefik/traefik/pkgs/container/traefik",
        "description": "Cloud-native application proxy and load balancer.",
        "container_port": 80,
        "default_host_port": 8080,
        "icon": "🔀",
        "logo_domain": "traefik.io",
    },
    {
        "id": "ghcr-sonarr",
        "name": "Sonarr",
        "image": "ghcr.io/linuxserver/sonarr:latest",
        "namespace": "linuxserver",
        "hub_name": "sonarr",
        "github_owner": "linuxserver",
        "github_package": "sonarr",
        "github_repo": "linuxserver/docker-sonarr",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/linuxserver/docker-sonarr/pkgs/container/sonarr",
        "description": "Smart PVR for Usenet and BitTorrent users.",
        "container_port": 8989,
        "default_host_port": 8989,
        "icon": "📺",
        "logo_domain": "sonarr.tv",
    },
    {
        "id": "ghcr-radarr",
        "name": "Radarr",
        "image": "ghcr.io/linuxserver/radarr:latest",
        "namespace": "linuxserver",
        "hub_name": "radarr",
        "github_owner": "linuxserver",
        "github_package": "radarr",
        "github_repo": "linuxserver/docker-radarr",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/linuxserver/docker-radarr/pkgs/container/radarr",
        "description": "Movie collection manager for Usenet and BitTorrent.",
        "container_port": 7878,
        "default_host_port": 7878,
        "icon": "🎬",
        "logo_domain": "radarr.video",
    },
    {
        "id": "ghcr-jellyfin",
        "name": "Jellyfin",
        "image": "ghcr.io/linuxserver/jellyfin:latest",
        "namespace": "linuxserver",
        "hub_name": "jellyfin",
        "github_owner": "linuxserver",
        "github_package": "jellyfin",
        "github_repo": "linuxserver/docker-jellyfin",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/linuxserver/docker-jellyfin/pkgs/container/jellyfin",
        "description": "Free software media system for streaming.",
        "container_port": 8096,
        "default_host_port": 8096,
        "icon": "🎞️",
        "logo_domain": "jellyfin.org",
    },
    {
        "id": "ghcr-otel-collector",
        "name": "OpenTelemetry Collector",
        "image": "ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:latest",
        "namespace": "open-telemetry",
        "hub_name": "opentelemetry-collector-contrib",
        "github_owner": "open-telemetry",
        "github_package": "opentelemetry-collector-releases/opentelemetry-collector-contrib",
        "github_repo": "open-telemetry/opentelemetry-collector-releases",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/open-telemetry/opentelemetry-collector-releases/pkgs/container/opentelemetry-collector-releases%2Fopentelemetry-collector-contrib",
        "description": "Vendor-neutral observability pipeline for metrics, logs, and traces.",
        "container_port": 4317,
        "default_host_port": 4317,
        "icon": "📡",
        "logo_domain": "opentelemetry.io",
    },
    {
        "id": "ghcr-flux",
        "name": "Flux CLI",
        "image": "ghcr.io/fluxcd/flux-cli:latest",
        "namespace": "fluxcd",
        "hub_name": "flux-cli",
        "github_owner": "fluxcd",
        "github_package": "flux-cli",
        "github_repo": "fluxcd/flux2",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/fluxcd/flux2/pkgs/container/flux-cli",
        "description": "GitOps toolkit for Kubernetes continuous delivery.",
        "icon": "☸️",
        "logo_domain": "fluxcd.io",
    },
    {
        "id": "ghcr-actions-runner",
        "name": "GitHub Actions Runner",
        "image": "ghcr.io/actions/actions-runner:latest",
        "namespace": "actions",
        "hub_name": "actions-runner",
        "github_owner": "actions",
        "github_package": "actions-runner",
        "github_repo": "actions/runner",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/actions/runner/pkgs/container/actions-runner",
        "description": "Self-hosted runner image for GitHub Actions workflows.",
        "icon": "⚙️",
        "logo_domain": "github.com",
    },
    {
        "id": "ghcr-super-linter",
        "name": "Super Linter",
        "image": "ghcr.io/super-linter/super-linter:latest",
        "namespace": "super-linter",
        "hub_name": "super-linter",
        "github_owner": "super-linter",
        "github_package": "super-linter",
        "github_repo": "super-linter/super-linter",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/super-linter/super-linter/pkgs/container/super-linter",
        "description": "Combines multiple linters for CI code quality checks.",
        "icon": "🔍",
        "logo_domain": "github.com",
    },
    {
        "id": "ghcr-nginx",
        "name": "NGINX (nginxinc)",
        "image": "ghcr.io/nginxinc/nginx-unprivileged:latest",
        "namespace": "nginxinc",
        "hub_name": "nginx-unprivileged",
        "github_owner": "nginxinc",
        "github_package": "nginx-unprivileged",
        "github_repo": "nginxinc/docker-nginx-unprivileged",
        "github_is_org": True,
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": "https://github.com/nginxinc/docker-nginx-unprivileged/pkgs/container/nginx-unprivileged",
        "description": "Unprivileged NGINX image for non-root container deployments.",
        "container_port": 8080,
        "default_host_port": 8080,
        "icon": "🌐",
        "logo_domain": "nginx.org",
    },
]

ALL_CATALOG_REPOS = POPULAR_REPOS + POPULAR_GHCR_REPOS


def parse_port_mapping(port_str):
    """Parse '8080:80' or '80' into docker port format."""
    port_str = port_str.strip()
    if not port_str:
        return None
    if ":" in port_str:
        host, container = port_str.split(":", 1)
        return {f"{container.strip()}/tcp": int(host.strip())}
    return {f"{port_str}/tcp": int(port_str)}


def format_count(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "0"
    if number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f}B"
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}K"
    return str(number)


def logo_url_for_repo(repo):
    domain = repo.get("logo_domain") or "docker.com"
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


def hub_repo_path(namespace, name):
    return f"{namespace}/{name}"


def hub_page_url(namespace, name):
    if namespace == "library":
        return f"https://hub.docker.com/_/{name}"
    return f"https://hub.docker.com/r/{namespace}/{name}"


def github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def normalize_registry(registry):
    registry = (registry or REGISTRY_DOCKER_HUB).strip().lower()
    if registry in ("ghcr", "github", "github-container-registry"):
        return REGISTRY_GHCR
    return REGISTRY_DOCKER_HUB


def fetch_hub_repo_stats(namespace, name):
    slug = hub_repo_path(namespace, name)
    try:
        resp = requests.get(f"{HUB_API}/repositories/{slug}/", timeout=REGISTRY_TIMEOUT)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        return {
            "pull_count": data.get("pull_count", 0),
            "star_count": data.get("star_count", 0),
            "description": data.get("description") or data.get("short_description") or "",
        }
    except requests.RequestException:
        return {}


def fetch_ghcr_repo_stats(repo):
    owner = repo.get("github_owner") or repo.get("namespace")
    package_name = repo.get("github_package") or repo.get("hub_name")
    is_org = repo.get("github_is_org", True)
    owner_type = "orgs" if is_org else "users"
    stats = {}

    try:
        resp = requests.get(
            f"{GITHUB_API}/{owner_type}/{owner}/packages/container/{package_name}",
            headers=github_headers(),
            timeout=REGISTRY_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            stats["description"] = data.get("description") or ""
            stats["registry_url"] = data.get("html_url") or repo.get("registry_url")
    except requests.RequestException:
        pass

    github_repo = repo.get("github_repo")
    if github_repo:
        try:
            resp = requests.get(
                f"{GITHUB_API}/repos/{github_repo}",
                headers=github_headers(),
                timeout=REGISTRY_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                stats["star_count"] = data.get("stargazers_count", 0)
                stats["description"] = stats.get("description") or data.get("description") or ""
        except requests.RequestException:
            pass

    return stats


def enrich_repo(repo, live_stats=None):
    registry_id = repo.get("registry_id", REGISTRY_DOCKER_HUB)
    if registry_id == REGISTRY_GHCR:
        stats = live_stats or fetch_ghcr_repo_stats(repo)
        pull_count = stats.get("pull_count", repo.get("pull_count"))
        star_count = stats.get("star_count", repo.get("star_count", 0))
        pull_label = format_count(pull_count) if pull_count is not None else "—"
    else:
        stats = live_stats or fetch_hub_repo_stats(repo.get("namespace", "library"), repo["hub_name"])
        pull_count = stats.get("pull_count", repo.get("pull_count", 0))
        star_count = stats.get("star_count", repo.get("star_count", 0))
        pull_label = format_count(pull_count)

    description = stats.get("description") or repo.get("description", "")
    enriched = {
        **repo,
        "registry_id": registry_id,
        "description": description,
        "pull_count": pull_count,
        "star_count": star_count,
        "pull_count_label": pull_label,
        "star_count_label": format_count(star_count),
        "logo_url": logo_url_for_repo(repo),
        "registry_url": stats.get("registry_url") or repo.get("registry_url") or (
            hub_page_url(repo.get("namespace", "library"), repo["hub_name"])
            if registry_id == REGISTRY_DOCKER_HUB
            else f"https://github.com/{repo.get('github_owner', repo.get('namespace'))}/pkgs/container/{repo.get('github_package', repo.get('hub_name'))}"
        ),
    }
    return enriched


def search_result_to_repo(result):
    repo_name = result.get("repo_name", "")
    if "/" in repo_name:
        namespace, name = repo_name.split("/", 1)
    else:
        namespace, name = "library", repo_name

    pull_count = result.get("pull_count", 0)
    star_count = result.get("star_count", 0)
    repo = {
        "id": repo_name.replace("/", "-").lower(),
        "name": name if namespace != "library" else name.upper() if len(name) <= 5 else name.title(),
        "image": f"{repo_name}:latest",
        "namespace": namespace,
        "hub_name": name,
        "registry": "Docker Hub",
        "registry_id": REGISTRY_DOCKER_HUB,
        "registry_url": hub_page_url(namespace, name),
        "description": result.get("short_description") or "",
        "pull_count": pull_count,
        "star_count": star_count,
        "pull_count_label": format_count(pull_count),
        "star_count_label": format_count(star_count),
        "icon": "🐳",
        "logo_url": logo_url_for_repo({"logo_domain": "docker.com"}),
        "is_official": result.get("is_official", False),
        "container_port": 80,
        "default_host_port": 8080,
    }
    return repo


def ghcr_package_url(owner, package_name):
    encoded = package_name.replace("/", "%2F")
    return f"https://github.com/{owner}/pkgs/container/{encoded}"


def search_result_to_ghcr_repo(result):
    owner = result.get("owner", {}).get("login", "")
    name = result.get("name", "")
    if not owner or not name:
        return None

    stars = result.get("stargazers_count", 0)
    image = f"ghcr.io/{owner}/{name}:latest"
    repo = {
        "id": f"ghcr-{owner}-{name}".replace("/", "-").lower(),
        "name": name.replace("-", " ").title(),
        "image": image,
        "namespace": owner,
        "hub_name": name,
        "github_owner": owner,
        "github_package": name,
        "github_repo": f"{owner}/{name}",
        "github_is_org": result.get("owner", {}).get("type") == "Organization",
        "registry": "GitHub Container Registry",
        "registry_id": REGISTRY_GHCR,
        "registry_url": ghcr_package_url(owner, name),
        "description": result.get("description") or "",
        "star_count": stars,
        "star_count_label": format_count(stars),
        "pull_count": None,
        "pull_count_label": "—",
        "icon": "🐙",
        "logo_url": logo_url_for_repo({"logo_domain": "github.com"}),
        "container_port": 80,
        "default_host_port": 8080,
    }
    return repo


def search_ghcr_catalog(query):
    try:
        resp = requests.get(
            f"{GITHUB_API}/search/repositories",
            params={
                "q": f"{query} in:name,description,readme",
                "sort": "stars",
                "order": "desc",
                "per_page": 20,
            },
            headers=github_headers(),
            timeout=REGISTRY_TIMEOUT,
        )
        resp.raise_for_status()
        repos = []
        for item in resp.json().get("items", []):
            mapped = search_result_to_ghcr_repo(item)
            if mapped:
                repos.append(mapped)
        return repos
    except requests.RequestException as e:
        raise RuntimeError(f"GHCR search failed: {e}") from e


def get_catalog_repo(repo_id):
    for repo in ALL_CATALOG_REPOS:
        if repo["id"] == repo_id:
            return repo
    return None


def catalog_for_registry(registry):
    if registry == REGISTRY_GHCR:
        return POPULAR_GHCR_REPOS
    return POPULAR_REPOS


def resolve_deploy_repo(data):
    repo_id = (data.get("id") or "").strip()
    if repo_id:
        repo = get_catalog_repo(repo_id)
        if repo:
            return repo

    image = (data.get("image") or "").strip()
    if not image:
        return None

    repo = {
        "id": repo_id or image.replace("/", "-").replace(":", "-"),
        "name": (data.get("name") or image.split("/")[-1].split(":")[0]).strip(),
        "image": image,
        "container_port": data.get("container_port"),
        "default_host_port": data.get("host_port") or data.get("default_host_port") or 8080,
        "env_defaults": data.get("env_defaults") or {},
    }
    if repo["container_port"] in ("", None):
        repo["container_port"] = None
    return repo


def validate_port(port):
    try:
        value = int(port)
        return 1 <= value <= 65535
    except (TypeError, ValueError):
        return False


def find_image(ref):
    ref = (ref or "").strip()
    if not ref:
        return None

    try:
        return client.images.get(ref)
    except ImageNotFound:
        pass

    ref_lower = ref.lower()
    for img in client.images.list():
        if img.id == ref or img.short_id == ref:
            return img
        if img.id.lower() == ref_lower:
            return img
        if ref in (img.tags or []):
            return img
        if ref.startswith("sha256:") and img.id.startswith(ref):
            return img
        if not ref.startswith("sha256:") and img.short_id.endswith(ref):
            return img
    return None


def remove_image_ref(ref, force=False):
    image = find_image(ref)
    if not image:
        raise ImageNotFound(f"Image '{ref}' not found")

    label = (image.tags[0] if image.tags else image.short_id)
    client.images.remove(image.id, force=force)
    return label


def ensure_image(image):
    try:
        client.images.get(image)
        return False
    except ImageNotFound:
        client.images.pull(image)
        return True


def build_run_kwargs(image, name=None, host_port=None, container_port=None, env=None, command=None):
    kwargs = {"detach": True}
    if name:
        kwargs["name"] = name
    if command:
        kwargs["command"] = command.split()
    if env:
        kwargs["environment"] = env
    if host_port is not None and container_port is not None:
        kwargs["ports"] = {f"{container_port}/tcp": int(host_port)}
    return kwargs


def parse_env_vars(env_str):
    if not env_str or not env_str.strip():
        return None
    return [line.strip() for line in env_str.strip().splitlines() if "=" in line.strip()]


def container_image_label(c):
    image = c.attrs.get("Config", {}).get("Image") or c.attrs.get("Image", "unknown")
    if image.startswith("sha256:"):
        return image[:19]
    return image


def format_size(size_bytes):
    if not size_bytes:
        return "0 B"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def container_to_dict(c):
    ports = []
    if c.ports:
        for container_port, bindings in c.ports.items():
            if bindings:
                for b in bindings:
                    ports.append(f"{b.get('HostIp', '0.0.0.0')}:{b['HostPort']}->{container_port}")
            else:
                ports.append(container_port)

    source = detect_update_source(c)
    return {
        "id": c.short_id,
        "name": c.name.lstrip("/"),
        "image": container_image_label(c),
        "status": c.status,
        "state": c.attrs.get("State", {}).get("Status", "unknown"),
        "running": c.status == "running",
        "created": c.attrs.get("Created", ""),
        "ports": ports,
        "can_pull_latest": source["can_pull_latest"],
        "update_source": source["update_source"],
        "update_source_label": source.get("update_source_label"),
        "compose_service": source.get("compose_service"),
        "github_repo": source.get("github_repo"),
    }


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def container_labels(c):
    return (c.attrs.get("Config") or {}).get("Labels") or c.attrs.get("Labels") or {}


def detect_update_source(c):
    labels = container_labels(c)
    working_dir = labels.get(COMPOSE_LABEL_WORKDIR) or ""
    service = labels.get(COMPOSE_LABEL_SERVICE) or ""
    if working_dir and service and os.path.isdir(working_dir):
        git_path = os.path.join(working_dir, ".git")
        if os.path.exists(git_path):
            slug = git_origin_slug(working_dir)
            return {
                "can_pull_latest": True,
                "update_source": "github",
                "update_source_label": "GitHub",
                "compose_service": service,
                "github_repo": slug,
            }
        return {
            "can_pull_latest": True,
            "update_source": "compose",
            "update_source_label": "Compose",
            "compose_service": service,
            "github_repo": None,
        }

    image = container_image_label(c)
    if image and not str(image).startswith("sha256:"):
        return {
            "can_pull_latest": True,
            "update_source": "registry",
            "update_source_label": "Registry",
            "compose_service": None,
            "github_repo": None,
        }
    return {
        "can_pull_latest": False,
        "update_source": None,
        "update_source_label": None,
        "compose_service": None,
        "github_repo": None,
    }


def compose_info(container):
    labels = container_labels(container)
    working_dir = labels.get(COMPOSE_LABEL_WORKDIR) or ""
    service = labels.get(COMPOSE_LABEL_SERVICE) or ""
    project = labels.get(COMPOSE_LABEL_PROJECT) or ""
    config_files = [
        path.strip()
        for path in (labels.get(COMPOSE_LABEL_CONFIG) or "").split(",")
        if path.strip()
    ]
    if not working_dir or not service or not os.path.isdir(working_dir):
        return None
    return {
        "working_dir": working_dir,
        "service": service,
        "project": project,
        "config_files": config_files,
    }


def split_image_ref(ref):
    ref = (ref or "").strip()
    if not ref or ref.startswith("sha256:"):
        return None, None
    if "@" in ref:
        return ref, None
    slash = ref.rfind("/")
    colon = ref.rfind(":")
    if colon > slash:
        return ref[:colon], ref[colon + 1:]
    return ref, "latest"


def pull_auth_for_image(repository):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token and (repository or "").startswith("ghcr.io/"):
        username = os.environ.get("GITHUB_USER", "").strip() or "oauth2"
        return {"username": username, "password": token}
    return None


def job_path(job_id):
    return os.path.join(JOBS_DIR, f"{job_id}.json")


def save_job(job):
    os.makedirs(JOBS_DIR, exist_ok=True)
    path = job_path(job["id"])
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(job, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def load_job(job_id):
    path = job_path(job_id)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def find_running_pull_job(container_id, container_name):
    if not os.path.isdir(JOBS_DIR):
        return None
    for name in os.listdir(JOBS_DIR):
        if not name.endswith(".json"):
            continue
        try:
            job = load_job(name[:-5])
        except (OSError, json.JSONDecodeError):
            continue
        if not job or job.get("status") != "running":
            continue
        if job.get("container_id") == container_id or job.get("container_name") == container_name:
            return job
    return None


def job_log(job, line):
    text = (line or "").rstrip()
    if not text:
        return
    logs = job.setdefault("logs", [])
    logs.append(text)
    if len(logs) > 500:
        job["logs"] = logs[:40] + ["… (log truncated) …"] + logs[-450:]
    save_job(job)


def new_pull_job(container):
    job = {
        "id": uuid.uuid4().hex[:12],
        "status": "running",
        "container_id": container.short_id,
        "container_name": container.name.lstrip("/"),
        "image": container_image_label(container),
        "source": detect_update_source(container)["update_source"],
        "logs": [],
        "message": "Starting Pull Latest…",
        "updated": False,
        "container": None,
        "started_at": utc_now(),
        "finished_at": None,
    }
    save_job(job)
    return job


def run_logged_command(cmd, job, cwd=None, env=None, timeout=PULL_TIMEOUT):
    job_log(job, f"$ {' '.join(cmd)}")
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            env=merged_env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {cmd[0]}") from exc

    assert proc.stdout is not None
    for line in proc.stdout:
        job_log(job, line)
    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(cmd)}") from exc
    if returncode != 0:
        raise RuntimeError(f"Command failed ({returncode}): {' '.join(cmd)}")
    return returncode


def is_git_repo(path):
    if not shutil.which("git"):
        return False
    result = subprocess.run(
        ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_capture(working_dir, args):
    result = subprocess.run(
        ["git", "-C", working_dir, *args],
        capture_output=True,
        text=True,
        errors="replace",
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def git_rev_parse(working_dir, *args):
    return git_capture(working_dir, ["rev-parse", *args])


def parse_github_slug(url):
    url = (url or "").strip()
    url = url.replace("git@github.com:", "https://github.com/")
    url = re.sub(r"^ssh://git@github\.com/", "https://github.com/", url)
    url = re.sub(r"\.git$", "", url)
    match = re.search(r"github\.com[/:]([^/]+)/([^/]+)", url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def git_origin_slug(working_dir):
    if not working_dir or not is_git_repo(working_dir):
        return None
    code, url, _ = git_capture(working_dir, ["remote", "get-url", "origin"])
    if code != 0:
        return None
    return parse_github_slug(url)


def fetch_github_latest_release(slug):
    if not slug or "/" not in slug:
        return None
    try:
        resp = requests.get(
            f"{GITHUB_API}/repos/{slug}/releases/latest",
            headers=github_headers(),
            timeout=REGISTRY_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag = data.get("tag_name")
        if not tag:
            return None
        return {
            "tag": tag,
            "name": data.get("name") or tag,
            "html_url": data.get("html_url") or "",
        }
    except requests.RequestException:
        return None


def git_has_tracked_changes(working_dir):
    code, output, _ = git_capture(working_dir, ["status", "--porcelain"])
    if code != 0:
        return False
    for line in output.splitlines():
        if line.startswith("??") or line.startswith("!!"):
            continue
        if line.strip():
            return True
    return False


def git_ref_exists(working_dir, ref):
    code, _, _ = git_capture(working_dir, ["rev-parse", "--verify", "--quiet", ref])
    return code == 0


def git_is_ancestor(working_dir, ancestor, descendant):
    code, _, _ = git_capture(working_dir, ["merge-base", "--is-ancestor", ancestor, descendant])
    return code == 0


def git_pull_latest(working_dir, job):
    if not shutil.which("git"):
        raise RuntimeError("git is not installed on the host")
    if not is_git_repo(working_dir):
        return None

    env = {
        "GIT_TERMINAL_PROMPT": "0",
    }
    run_logged_command(
        ["git", "-C", working_dir, "status", "-sb"],
        job,
        env=env,
        timeout=60,
    )
    run_logged_command(
        ["git", "-C", working_dir, "fetch", "--tags", "--prune", "origin"],
        job,
        env=env,
        timeout=120,
    )

    code, branch, _ = git_rev_parse(working_dir, "--abbrev-ref", "HEAD")
    if code != 0 or not branch or branch == "HEAD":
        raise RuntimeError("Git repository is in a detached HEAD state; cannot pull latest")
    code, before, _ = git_rev_parse(working_dir, "HEAD")
    if code != 0:
        raise RuntimeError("Could not read current git commit")

    slug = git_origin_slug(working_dir)
    if slug:
        job_log(job, f"GitHub repo: {slug}")

    stashed = False
    if git_has_tracked_changes(working_dir):
        job_log(job, "Stashing local tracked changes so GitHub can be pulled")
        run_logged_command(
            ["git", "-C", working_dir, "stash", "push", "-m", "dockview-pull-latest"],
            job,
            env=env,
            timeout=60,
        )
        stashed = True

    release = None
    try:
        upstream_code, _, _ = git_rev_parse(working_dir, "--abbrev-ref", "@{u}")
        if upstream_code == 0:
            pull_cmd = ["git", "-C", working_dir, "pull", "--ff-only", "--autostash"]
        else:
            pull_cmd = ["git", "-C", working_dir, "merge", "--ff-only", f"origin/{branch}"]
        run_logged_command(pull_cmd, job, env=env, timeout=120)

        if slug:
            release = fetch_github_latest_release(slug)
        if release:
            tag = release["tag"]
            job_log(job, f"Latest GitHub release: {release['name']} ({tag})")
            tag_ref = tag if git_ref_exists(working_dir, tag) else (
                f"refs/tags/{tag}" if git_ref_exists(working_dir, f"refs/tags/{tag}") else None
            )
            if not tag_ref:
                job_log(job, f"Release tag {tag} is not in this repository after fetch")
            elif git_is_ancestor(working_dir, "HEAD", tag_ref) and not git_is_ancestor(working_dir, tag_ref, "HEAD"):
                job_log(job, f"Fast-forwarding to GitHub release {tag}")
                run_logged_command(
                    ["git", "-C", working_dir, "merge", "--ff-only", tag_ref],
                    job,
                    env=env,
                    timeout=60,
                )
            elif git_is_ancestor(working_dir, tag_ref, "HEAD"):
                job_log(job, f"Current codebase is at or ahead of release {tag}")
            else:
                job_log(job, f"Release {tag} diverges from {branch}; keeping latest {branch} codebase")
        else:
            job_log(job, "No GitHub release found; using latest codebase")
    finally:
        if stashed:
            pop = subprocess.run(
                ["git", "-C", working_dir, "stash", "pop"],
                capture_output=True,
                text=True,
                errors="replace",
                env={**os.environ, **env},
            )
            if pop.stdout:
                job_log(job, pop.stdout)
            if pop.stderr:
                job_log(job, pop.stderr)
            if pop.returncode != 0:
                job_log(job, "Warning: could not restore stashed local changes automatically")

    _, after, _ = git_rev_parse(working_dir, "HEAD")
    subject = git_capture(working_dir, ["log", "-1", "--pretty=%s"])[1]
    updated = before != after
    if updated:
        job_log(job, f"Git updated {before[:10]} → {after[:10]} on {branch}: {subject}")
    else:
        job_log(job, f"Git already up to date at {after[:10]} ({branch})")
    result = {
        "before": before,
        "after": after,
        "updated": updated,
        "branch": branch,
        "subject": subject,
        "github_repo": slug,
    }
    if release:
        result["release"] = release
    return result


def compose_rebuild(info, job):
    if not shutil.which("docker"):
        raise RuntimeError("docker CLI is not installed on the host")
    cmd = ["docker", "compose"]
    if info.get("project"):
        cmd += ["-p", info["project"]]
    for compose_file in info.get("config_files") or []:
        cmd += ["-f", compose_file]
    cmd += [
        "up", "-d",
        "--build",
        "--pull", "always",
        "--force-recreate",
        "--no-deps",
        info["service"],
    ]
    env = {
        "COMPOSE_ANSI": "never",
        "DOCKER_CLI_HINTS": "false",
        "BUILDKIT_PROGRESS": "plain",
    }
    run_logged_command(cmd, job, cwd=info["working_dir"], env=env, timeout=PULL_TIMEOUT)


def extra_hosts_to_dict(extra_hosts):
    if not extra_hosts:
        return None
    if isinstance(extra_hosts, dict):
        return extra_hosts
    mapping = {}
    for item in extra_hosts:
        if ":" not in item:
            continue
        host, ip = item.split(":", 1)
        mapping[host] = ip
    return mapping or None


def extract_run_kwargs(container):
    attrs = container.attrs or {}
    config = attrs.get("Config") or {}
    host = attrs.get("HostConfig") or {}
    kwargs = {"name": container.name.lstrip("/")}

    env = config.get("Env")
    if env:
        kwargs["environment"] = env
    if config.get("Cmd"):
        kwargs["command"] = config["Cmd"]
    if config.get("Entrypoint"):
        kwargs["entrypoint"] = config["Entrypoint"]
    if config.get("WorkingDir"):
        kwargs["working_dir"] = config["WorkingDir"]
    if config.get("User"):
        kwargs["user"] = config["User"]
    if config.get("Labels"):
        kwargs["labels"] = config["Labels"]
    if config.get("Tty"):
        kwargs["tty"] = True
    if config.get("OpenStdin"):
        kwargs["stdin_open"] = True

    ports = {}
    for container_port, bindings in (host.get("PortBindings") or {}).items():
        if not bindings:
            continue
        binding = bindings[0] or {}
        host_port = binding.get("HostPort")
        if not host_port:
            continue
        host_ip = binding.get("HostIp") or ""
        if host_ip and host_ip not in ("0.0.0.0", "::"):
            ports[container_port] = (host_ip, int(host_port))
        else:
            ports[container_port] = int(host_port)
    if ports:
        kwargs["ports"] = ports

    binds = host.get("Binds")
    if binds:
        kwargs["volumes"] = binds
    else:
        volumes = []
        for mount in attrs.get("Mounts") or []:
            dest = mount.get("Destination")
            if not dest:
                continue
            mode = "ro" if not mount.get("RW", True) else "rw"
            if mount.get("Type") == "bind" and mount.get("Source"):
                volumes.append(f"{mount['Source']}:{dest}:{mode}")
            elif mount.get("Type") == "volume" and mount.get("Name"):
                volumes.append(f"{mount['Name']}:{dest}:{mode}")
        if volumes:
            kwargs["volumes"] = volumes

    restart_policy = host.get("RestartPolicy") or {}
    if restart_policy.get("Name"):
        kwargs["restart_policy"] = restart_policy

    network_mode = host.get("NetworkMode") or ""
    if network_mode in ("host", "none"):
        kwargs["network_mode"] = network_mode
    elif network_mode.startswith("container:"):
        kwargs["network_mode"] = network_mode
    elif network_mode and network_mode not in ("default", "bridge"):
        kwargs["network"] = network_mode

    if host.get("Privileged"):
        kwargs["privileged"] = True
    if host.get("CapAdd"):
        kwargs["cap_add"] = host["CapAdd"]
    if host.get("CapDrop"):
        kwargs["cap_drop"] = host["CapDrop"]
    extra_hosts = extra_hosts_to_dict(host.get("ExtraHosts"))
    if extra_hosts:
        kwargs["extra_hosts"] = extra_hosts
    if host.get("Dns"):
        kwargs["dns"] = host["Dns"]
    if host.get("AutoRemove"):
        kwargs["auto_remove"] = True
    memory = host.get("Memory") or 0
    if memory:
        kwargs["mem_limit"] = memory
    return kwargs


def pull_registry_image(image_ref, job):
    repo, tag = split_image_ref(image_ref)
    if not repo:
        raise RuntimeError(f"Image '{image_ref}' cannot be pulled (digest-only reference)")

    display = f"{repo}:{tag}" if tag else repo
    job_log(job, f"Pulling {display} from registry…")
    auth = pull_auth_for_image(repo)
    pull_kwargs = {"stream": True, "decode": True}
    if auth:
        pull_kwargs["auth_config"] = auth

    if tag:
        events = client.api.pull(repo, tag=tag, **pull_kwargs)
    else:
        events = client.api.pull(repo, **pull_kwargs)

    last_status = {}
    error = None
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("error"):
            error = event["error"]
            break
        status = event.get("status") or ""
        layer_id = event.get("id") or ""
        if event.get("progress"):
            continue
        line = " ".join(part for part in (layer_id, status) if part).strip()
        if line and last_status.get(layer_id) != status:
            job_log(job, line)
            last_status[layer_id] = status
    if error:
        raise RuntimeError(error)

    try:
        pulled = client.images.get(image_ref)
    except ImageNotFound:
        pulled = client.images.get(display)
    job_log(job, f"Image ready: {pulled.short_id}")
    return pulled


def recreate_container_with_image(container, image_ref, job):
    was_running = container.status == "running"
    old_name = container.name.lstrip("/")
    backup_name = f"{old_name}-dockview-old-{container.short_id}"
    kwargs = extract_run_kwargs(container)
    kwargs["name"] = old_name
    job_log(job, f"Recreating '{old_name}' with {image_ref}…")

    if was_running:
        job_log(job, f"Stopping '{old_name}' to release ports and volumes")
        container.stop(timeout=10)
    container.rename(backup_name)
    new_container = None
    try:
        new_container = client.containers.create(image_ref, **kwargs)
        if was_running:
            new_container.start()
        new_container.reload()
        container.reload()
        container.remove(force=True)
        job_log(job, f"Replaced previous container {container.short_id}")
        return new_container
    except Exception:
        job_log(job, "Recreate failed — rolling back to the previous container")
        if new_container is not None:
            try:
                new_container.remove(force=True)
            except APIError:
                pass
        try:
            container.reload()
            container.rename(old_name)
            if was_running and container.status != "running":
                container.start()
        except APIError as rollback_error:
            job_log(job, f"Rollback failed: {rollback_error}")
        raise


def finish_job(job, status, message, container=None, updated=False):
    job["status"] = status
    job["message"] = message
    job["updated"] = updated
    job["finished_at"] = utc_now()
    if container is not None:
        try:
            container.reload()
            job["container"] = container_to_dict(container)
        except (NotFound, APIError):
            job["container"] = None
    save_job(job)


def run_pull_latest_job(job_id, container_id):
    job = load_job(job_id)
    if not job:
        return
    try:
        container = client.containers.get(container_id)
        container.reload()
        info = compose_info(container)
        image_ref = container.attrs.get("Config", {}).get("Image") or container_image_label(container)
        job["image"] = image_ref
        save_job(job)

        if info:
            job["source"] = "github" if is_git_repo(info["working_dir"]) else "compose"
            save_job(job)
            job_log(job, f"Compose service '{info['service']}' in {info['working_dir']}")
            if is_git_repo(info["working_dir"]):
                git_info = git_pull_latest(info["working_dir"], job)
                if git_info:
                    job["git"] = git_info
                    save_job(job)
            else:
                job_log(job, "No git repository found — rebuilding from local source")
            job_log(job, "Rebuilding and recreating with Docker Compose…")
            compose_rebuild(info, job)
            try:
                container = client.containers.get(job["container_name"])
            except NotFound:
                container = client.containers.get(container_id)
            finish_job(
                job,
                "success",
                f"Pulled latest and recreated '{job['container_name']}'",
                container=container,
                updated=True,
            )
            return

        if not image_ref or str(image_ref).startswith("sha256:"):
            raise RuntimeError("Container has no pullable image tag")

        old_image_id = container.attrs.get("Image")
        pulled = pull_registry_image(image_ref, job)
        if pulled.id == old_image_id:
            finish_job(
                job,
                "success",
                f"'{job['container_name']}' is already running the latest {image_ref}",
                container=container,
                updated=False,
            )
            return

        new_container = recreate_container_with_image(container, image_ref, job)
        finish_job(
            job,
            "success",
            f"Pulled latest {image_ref} and recreated '{job['container_name']}'",
            container=new_container,
            updated=True,
        )
    except Exception as exc:
        message = str(getattr(exc, "explanation", None) or exc)
        if job:
            job_log(job, f"Error: {message}")
            finish_job(job, "error", message, updated=False)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def stats():
    containers = client.containers.list(all=True)
    running = sum(1 for c in containers if c.status == "running")
    images = client.images.list()
    return jsonify({
        "total_containers": len(containers),
        "running": running,
        "stopped": len(containers) - running,
        "images": len(images),
    })


@app.route("/api/containers")
def list_containers():
    containers = client.containers.list(all=True)
    result = [container_to_dict(c) for c in containers]
    result.sort(key=lambda x: (not x["running"], x["name"]))
    return jsonify(result)


@app.route("/api/images")
def list_images():
    images = client.images.list()
    result = []
    for img in images:
        tags = img.tags or [img.short_id]
        size = img.attrs.get("Size", 0)
        for tag in tags:
            result.append({
                "id": img.short_id,
                "image_id": img.id,
                "tag": tag,
                "size": size,
                "size_label": format_size(size),
            })
    result.sort(key=lambda x: x["tag"])
    return jsonify(result)


@app.route("/api/registries")
def list_registries():
    return jsonify(list(REGISTRIES.values()))


@app.route("/api/catalog")
def catalog():
    registry = normalize_registry(request.args.get("registry"))
    enriched = [enrich_repo(repo) for repo in catalog_for_registry(registry)]
    return jsonify(enriched)


@app.route("/api/catalog/search")
def search_catalog():
    query = (request.args.get("q") or "").strip()
    registry = normalize_registry(request.args.get("registry"))
    if not query:
        return jsonify([])

    try:
        if registry == REGISTRY_GHCR:
            results = search_ghcr_catalog(query)
            return jsonify(results)

        resp = requests.get(
            f"{HUB_API}/search/repositories/",
            params={"query": query, "page_size": 20},
            timeout=REGISTRY_TIMEOUT,
        )
        resp.raise_for_status()
        results = [search_result_to_repo(item) for item in resp.json().get("results", [])]
        return jsonify(results)
    except (requests.RequestException, RuntimeError) as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/catalog/deploy", methods=["POST"])
def deploy_catalog_repo():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    host_port = data.get("host_port")
    container_port = data.get("container_port")

    repo = resolve_deploy_repo(data)
    if not repo:
        return jsonify({"error": "Unknown repository"}), 404

    if container_port in ("", None):
        container_port = repo.get("container_port")
    else:
        container_port = int(container_port)

    if host_port is None or host_port == "":
        host_port = repo.get("default_host_port")
    if host_port not in (None, "") and not validate_port(host_port):
        return jsonify({"error": "Host port must be between 1 and 65535"}), 400

    deploy_id = repo.get("id") or "custom"
    if not name:
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", deploy_id).strip("-").lower()
        name = f"dockview-{safe_name or 'app'}"
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", name):
        return jsonify({"error": "Invalid container name"}), 400

    image = repo["image"]
    env = [f"{k}={v}" for k, v in repo.get("env_defaults", {}).items()]
    kwargs = build_run_kwargs(
        image,
        name=name,
        env=env or None,
    )
    if host_port not in (None, "") and container_port:
        kwargs["ports"] = {f"{int(container_port)}/tcp": int(host_port)}

    try:
        pulled = ensure_image(image)
        container = client.containers.run(image, **kwargs)
        container.reload()
        port_msg = f" on port {host_port}" if host_port not in (None, "") and container_port else ""
        return jsonify({
            "message": f"Deployed '{repo['name']}'{port_msg}",
            "pulled": pulled,
            "container": container_to_dict(container),
            "access_url": (
                f"http://localhost:{host_port}"
                if host_port not in (None, "") and container_port in (80, 8080, 8000, 3000)
                else None
            ),
        }), 201
    except APIError as e:
        return jsonify({"error": str(e.explanation or e)}), 400


@app.route("/api/containers", methods=["POST"])
def create_container():
    data = request.get_json() or {}
    image = (data.get("image") or "").strip()
    name = (data.get("name") or "").strip()
    ports_raw = (data.get("ports") or "").strip()
    env_raw = (data.get("env") or "").strip()
    command = (data.get("command") or "").strip() or None
    pull = data.get("pull", False)

    if not image:
        return jsonify({"error": "Image is required"}), 400
    if name and not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", name):
        return jsonify({"error": "Invalid container name"}), 400

    port_bindings = None
    if ports_raw:
        port_bindings = {}
        for part in ports_raw.split(","):
            parsed = parse_port_mapping(part)
            if parsed:
                port_bindings.update(parsed)

    env = parse_env_vars(env_raw)
    kwargs = build_run_kwargs(image, name=name or None, env=env, command=command)
    if port_bindings:
        kwargs["ports"] = port_bindings

    try:
        if pull:
            ensure_image(image)
        container = client.containers.run(image, **kwargs)
        return jsonify({"message": f"Container '{container.name}' created", "container": container_to_dict(container)}), 201
    except ImageNotFound:
        return jsonify({"error": f"Image '{image}' not found. Pull it first or use an existing image."}), 404
    except APIError as e:
        return jsonify({"error": str(e.explanation or e)}), 400


@app.route("/api/containers/<container_id>/start", methods=["POST"])
def start_container(container_id):
    try:
        c = client.containers.get(container_id)
        c.start()
        c.reload()
        return jsonify({"message": f"Container '{c.name}' started", "container": container_to_dict(c)})
    except NotFound:
        return jsonify({"error": "Container not found"}), 404
    except APIError as e:
        return jsonify({"error": str(e.explanation or e)}), 400


@app.route("/api/containers/<container_id>/stop", methods=["POST"])
def stop_container(container_id):
    try:
        c = client.containers.get(container_id)
        c.stop(timeout=10)
        c.reload()
        return jsonify({"message": f"Container '{c.name}' stopped", "container": container_to_dict(c)})
    except NotFound:
        return jsonify({"error": "Container not found"}), 404
    except APIError as e:
        return jsonify({"error": str(e.explanation or e)}), 400


@app.route("/api/containers/<container_id>/pull-latest", methods=["POST"])
def pull_latest_container(container_id):
    try:
        container = client.containers.get(container_id)
        container.reload()
    except NotFound:
        return jsonify({"error": "Container not found"}), 404

    source = detect_update_source(container)
    if not source["can_pull_latest"]:
        return jsonify({
            "error": "This container has no pullable image tag or GitHub/Compose source",
        }), 400

    existing = find_running_pull_job(container.short_id, container.name.lstrip("/"))
    if existing:
        return jsonify({
            "message": "A Pull Latest job is already running for this container",
            "job": existing,
        }), 202

    job = new_pull_job(container)
    job_log(job, f"Queued Pull Latest for '{job['container_name']}' ({source['update_source']})")
    thread = threading.Thread(
        target=run_pull_latest_job,
        args=(job["id"], container.id),
        daemon=True,
        name=f"dockview-pull-{job['id']}",
    )
    thread.start()
    return jsonify({
        "message": "Pull Latest started",
        "job": load_job(job["id"]),
    }), 202


@app.route("/api/jobs/<job_id>")
def get_job(job_id):
    if not re.match(r"^[a-f0-9]{12}$", job_id or ""):
        return jsonify({"error": "Invalid job id"}), 400
    job = load_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/containers/<container_id>", methods=["DELETE"])
def remove_container(container_id):
    force = request.args.get("force", "false").lower() == "true"
    try:
        c = client.containers.get(container_id)
        name = c.name
        c.remove(force=force)
        return jsonify({"message": f"Container '{name}' removed"})
    except NotFound:
        return jsonify({"error": "Container not found"}), 404
    except APIError as e:
        return jsonify({"error": str(e.explanation or e)}), 400


@app.route("/api/images/delete", methods=["POST"])
def delete_image():
    data = request.get_json() or {}
    ref = (data.get("ref") or data.get("image_id") or data.get("tag") or "").strip()
    force = bool(data.get("force", False))

    if not ref:
        return jsonify({"error": "Image reference is required"}), 400

    try:
        label = remove_image_ref(ref, force=force)
        return jsonify({"message": f"Image '{label}' removed"})
    except ImageNotFound:
        return jsonify({"error": f"Image '{ref}' not found"}), 404
    except APIError as e:
        error = str(e.explanation or e)
        if "must be forced" in error.lower() or "is using its referenced image" in error.lower():
            return jsonify({"error": error, "can_force": True}), 409
        return jsonify({"error": error}), 400


@app.route("/api/images/<path:image_ref>", methods=["DELETE"])
def remove_image(image_ref):
    force = request.args.get("force", "false").lower() == "true"
    try:
        label = remove_image_ref(image_ref, force=force)
        return jsonify({"message": f"Image '{label}' removed"})
    except ImageNotFound:
        return jsonify({"error": f"Image '{image_ref}' not found"}), 404
    except APIError as e:
        error = str(e.explanation or e)
        if "must be forced" in error.lower() or "is using its referenced image" in error.lower():
            return jsonify({"error": error, "can_force": True}), 409
        return jsonify({"error": error}), 400


@app.route("/api/images/pull", methods=["POST"])
def pull_image():
    data = request.get_json() or {}
    image = (data.get("image") or "").strip()
    if not image:
        return jsonify({"error": "Image name is required"}), 400
    try:
        result = client.images.pull(image)
        tag = result.tags[0] if result.tags else image
        return jsonify({"message": f"Image '{tag}' pulled successfully"})
    except APIError as e:
        return jsonify({"error": str(e.explanation or e)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port, debug=False)
