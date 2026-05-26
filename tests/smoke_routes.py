#!/usr/bin/env python3
"""Smoke-test service connectivity and route registration.

This checks that each FastAPI service is up, answers on /health,
and exposes the expected endpoint paths in OpenAPI.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


SERVICES = {
    "api_gateway": {
        "base_url": os.environ.get("API_GATEWAY_URL", "http://localhost:8000"),
        "required_paths": [
            "/health",
            "/api/auth/register",
            "/api/auth/login",
            "/api/users/me",
            "/api/users",
            "/api/users/{user_id}/keys",
            "/api/users/{user_id}/bundle",
            "/api/users/{user_id}/friends",
            "/api/chats",
            "/api/chats/{chat_id}",
            "/api/chats/{chat_id}/members",
            "/api/chats/{chat_id}/messages",
            "/api/messages/{message_id}",
            "/api/messages/{message_id}/read",
            "/api/profiles/{username}/picture",
            "/api/profiles/{username}/picture/complete",
            "/api/profiles/{username}/picture/metadata",
        ],
    },
    "auth_service": {
        "base_url": os.environ.get("AUTH_SERVICE_URL", "http://localhost:8001"),
        "required_paths": [
            "/health",
            "/api/auth/register",
            "/api/auth/login",
            "/api/users/me",
            "/api/users",
            "/api/users/{user_id}/keys",
            "/api/users/{user_id}/bundle",
            "/api/users/{user_id}/friends",
        ],
    },
    "chat_service": {
        "base_url": os.environ.get("CHAT_SERVICE_URL", "http://localhost:8002"),
        "required_paths": ["/health", "/api/chats", "/api/chats/{chat_id}", "/api/chats/{chat_id}/members"],
    },
    "message_service": {
        "base_url": os.environ.get("MESSAGE_SERVICE_URL", "http://localhost:8003"),
        "required_paths": [
            "/health",
            "/api/chats/{chat_id}/messages",
            "/api/messages/{message_id}",
            "/api/messages/{message_id}/read",
        ],
    },
    "media_service": {
        "base_url": os.environ.get("MEDIA_SERVICE_URL", "http://localhost:8004"),
        "required_paths": [
            "/health",
            "/api/profiles/{username}/picture",
            "/api/profiles/{username}/picture/complete",
            "/api/profiles/{username}/picture/metadata",
        ],
    },
}


def fetch_json(url: str, timeout: int = 10):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_health(base_url: str, service_name: str, timeout_seconds: int = 180):
    health_url = f"{base_url}/health"
    deadline = time.time() + timeout_seconds
    last_error = None

    while time.time() < deadline:
        try:
            data = fetch_json(health_url, timeout=5)
            if data.get("status") == "ok":
                return
            last_error = f"unexpected health payload: {data!r}"
        except Exception as exc:  # noqa: BLE001 - smoke test needs broad retry loop
            last_error = str(exc)
        time.sleep(2)

    raise RuntimeError(f"{service_name} did not become healthy: {last_error}")


def assert_required_paths(base_url: str, service_name: str, required_paths: list[str]):
    spec = fetch_json(f"{base_url}/openapi.json")
    available_paths = set(spec.get("paths", {}).keys())
    missing = [path for path in required_paths if path not in available_paths]
    if missing:
        raise AssertionError(f"{service_name} is missing routes: {', '.join(missing)}")


def main() -> int:
    for service_name, config in SERVICES.items():
        base_url = config["base_url"]
        print(f"Checking {service_name} at {base_url} ...")
        wait_for_health(base_url, service_name)
        assert_required_paths(base_url, service_name, config["required_paths"])
        print(f"{service_name}: ok")

    print("All service routes are registered and healthy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())