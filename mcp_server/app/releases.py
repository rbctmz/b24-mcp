from __future__ import annotations

import asyncio
import copy
import logging
import time
from typing import Any, Dict, List, Optional, Protocol

import httpx

from .settings import GitHubSettings

logger = logging.getLogger(__name__)

ReleaseEntry = Dict[str, Any]

RELEASE_VERSIONS: List[ReleaseEntry] = [
    {
        "version": "0.2.0",
        "status": "released",
        "title": "Release history API with GitHub sync",
        "notes": [
            "Added the `versions/releases` MCP resource so agents can read structured release notes over MCP.",
            "Documented the coverage in README/README_ru and hooked prompts for the new descriptor.",
            "Enabled `GITHUB_RELEASES_REPO`/`GITHUB_TOKEN`/timeout/cache controls to keep release data in sync with GitHub.",
        ],
    },
    {
        "version": "0.1.0",
        "status": "released",
        "title": "Initial public release",
        "notes": [
            "Resources for CRM deals, leads, contacts, tasks, users, dictionaries, and guides.",
            "Tools for listing CRM entities, creating tasks/comments, and updating deals.",
            "Responses include CallToolResult metadata, structured warnings, and pagination helpers.",
        ],
    },
    {
        "version": "Unreleased",
        "status": "draft",
        "title": "Incoming improvements",
        "notes": [
            "CallToolResult format applied to HTTP, JSON-RPC, SSE, and WebSocket flows while keeping structured content.",
            "getLeads leverages cached dictionaries and returns `_meta`, aggregates, copyable filters, and timezone-aware hints.",
            "Added callBitrixMethod for arbitrary REST proxying and getLeadCalls for enriched call logs.",
        ],
    },
]


class ReleaseSource(Protocol):
    """Abstract source of release metadata."""

    async def list_releases(self) -> List[ReleaseEntry]:
        ...


class StaticReleaseSource:
    """Static release list derived from CHANGELOG.md."""

    async def list_releases(self) -> List[ReleaseEntry]:
        return copy.deepcopy(RELEASE_VERSIONS)


def _notes_from_body(body: Optional[str]) -> List[str]:
    if not body:
        return []
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if lines:
        return lines
    stripped = body.strip()
    return [stripped] if stripped else []


class GitHubReleaseSource:
    """Fetch releases from a GitHub repository."""

    def __init__(self, settings: GitHubSettings, fallback: ReleaseSource | None = None) -> None:
        self._settings = settings
        self._fallback = fallback
        self._cache: List[ReleaseEntry] = []
        self._last_refresh: float = 0.0
        self._lock = asyncio.Lock()

    async def list_releases(self) -> List[ReleaseEntry]:
        if not self._settings.releases_repo:
            return await self._fallback.list_releases() if self._fallback else []

        now = time.monotonic()
        if self._cache and now - self._last_refresh < self._settings.cache_ttl_seconds:
            return copy.deepcopy(self._cache)

        async with self._lock:
            now = time.monotonic()
            if self._cache and now - self._last_refresh < self._settings.cache_ttl_seconds:
                return copy.deepcopy(self._cache)
            releases = await self._fetch_releases()
            if releases:
                self._cache = releases
                self._last_refresh = time.monotonic()
                return copy.deepcopy(releases)

        if self._fallback:
            return await self._fallback.list_releases()
        return []

    async def _fetch_releases(self) -> List[ReleaseEntry]:
        repo = self._settings.releases_repo.strip("/") if self._settings.releases_repo else ""
        if not repo:
            return []

        headers = {"Accept": "application/vnd.github+json"}
        if self._settings.token:
            headers["Authorization"] = f"Bearer {self._settings.token}"

        url = f"https://api.github.com/repos/{repo}/releases"
        params = {"per_page": 20}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._settings.timeout_seconds)) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("GitHub releases returned %s %s", exc.response.status_code, exc.response.text)
            return []
        except httpx.RequestError as exc:
            logger.warning("Failed to download GitHub releases: %s", exc)
            return []
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected error while fetching GitHub releases: %s", exc)
            return []

        if not isinstance(payload, list):
            return []

        entries: List[ReleaseEntry] = []
        for release in payload:
            if not isinstance(release, dict):
                continue
            status = "released"
            if release.get("draft"):
                status = "draft"
            elif release.get("prerelease"):
                status = "prerelease"
            title = release.get("name") or release.get("tag_name") or "Untitled release"
            entries.append(
                {
                    "version": release.get("tag_name") or title,
                    "status": status,
                    "title": title,
                    "notes": _notes_from_body(release.get("body")),
                    "url": release.get("html_url"),
                    "published_at": release.get("published_at"),
                }
            )
        return entries
