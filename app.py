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
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PULL_TIMEOUT = int(os.environ.get("DOCKVIEW_PULL_TIMEOUT", "1200"))
COMPOSE_LABEL_WORKDIR = "com.docker.compose.project.working_dir"
COMPOSE_LABEL_CONFIG = "com.docker.compose.project.config_files"
COMPOSE_LABEL_SERVICE = "com.docker.compose.service"
COMPOSE_LABEL_PROJECT = "com.docker.compose.project"

REGISTRY_DOCKER_HUB = "docker-hub"
REGISTRY_GHCR = "ghcr"
