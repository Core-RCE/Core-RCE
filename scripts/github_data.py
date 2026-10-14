"""Fetch a public GitHub profile snapshot using the standard library."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://api.github.com"
TIMEOUT_SECONDS = 15
MAX_RETRIES = 2
SCOPE = "public non-fork non-archived repositories, excluding profile repo"
_USERNAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}\Z")
_REPO_FIELDS = (
    "name",
    "description",
    "html_url",
    "language",
    "stargazers_count",
    "updated_at",
    "archived",
    "fork",
)


def _validate_username(username: str) -> None:
    if not isinstance(username, str) or not _USERNAME.fullmatch(username):
        raise ValueError(
            "GitHub username must be 1–39 ASCII letters, digits, or single "
            "hyphens, and cannot begin or end with a hyphen."
        )


def _request_json(path: str, *, token: str | None):
    """Request a path built locally; never follow a URL supplied in API data."""
    headers = {
        "User-Agent": "corerce-profile-readme",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(MAX_RETRIES + 1):
        request = Request(f"{API_ROOT}{path}", headers=headers)
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read()
        except HTTPError as exc:
            status = exc.code
            exc.close()
            if (status == 429 or 500 <= status <= 599) and attempt < MAX_RETRIES:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(
                f"GitHub API request failed for {path}: HTTP {status}."
            ) from None
        except (URLError, TimeoutError, OSError):
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(
                f"GitHub API request failed for {path}: network or timeout error."
            ) from None

        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError(
                f"GitHub API returned invalid JSON for {path}."
            ) from None

    raise RuntimeError(f"GitHub API request failed for {path}.")


def _check_repo(repo: object, path: str) -> dict:
    if (
        not isinstance(repo, dict)
        or not isinstance(repo.get("name"), str)
        or not repo["name"]
        or not isinstance(repo.get("fork"), bool)
        or not isinstance(repo.get("archived"), bool)
        or type(repo.get("stargazers_count")) is not int
        or repo["stargazers_count"] < 0
        or not isinstance(repo.get("updated_at"), str)
    ):
        raise RuntimeError(f"GitHub API returned invalid repository data for {path}.")
    return {field: repo.get(field) for field in _REPO_FIELDS}


def fetch_snapshot(username: str, *, token: str | None = None) -> dict:
    """Return real public profile, repository, and aggregate language data.

    Repository and language totals exclude registered forks, archived repositories, and
    the user's profile repository. ``public_repos`` is GitHub's account field,
    which can include repositories excluded from these aggregates.

    Validation errors raise ``ValueError``. API, network, or malformed-response
    errors raise ``RuntimeError`` rather than returning fabricated empty data.
    """
    _validate_username(username)
    owner = quote(username, safe="")
    profile_path = f"/users/{owner}"
    user = _request_json(profile_path, token=token)
    if not isinstance(user, dict):
        raise RuntimeError(f"GitHub API returned invalid user data for {profile_path}.")
    try:
        _validate_username(user.get("login"))
    except ValueError:
        raise RuntimeError(f"GitHub API returned invalid user data for {profile_path}.") from None

    profile = {
        "username": user["login"],
        **{
            field: user.get(field)
            for field in (
                "name",
                "bio",
                "avatar_url",
                "public_repos",
                "followers",
                "following",
                "created_at",
                "blog",
                "html_url",
            )
        },
    }

    repositories = []
    page = 1
    while True:
        query = urlencode({"per_page": 100, "page": page, "type": "owner"})
        path = f"/users/{owner}/repos?{query}"
        batch = _request_json(path, token=token)
        if not isinstance(batch, list):
            raise RuntimeError(f"GitHub API returned invalid repository data for {path}.")
        for raw_repo in batch:
            repo = _check_repo(raw_repo, path)
            if (
                repo["fork"]
                or repo["archived"]
                or repo["name"].casefold() == profile["username"].casefold()
            ):
                continue
            repositories.append(repo)
        if len(batch) < 100:
            break
        page += 1

    repositories.sort(
        key=lambda repo: (repo["stargazers_count"], repo["updated_at"]),
        reverse=True,
    )
    languages: dict[str, int] = {}
    for repo in repositories:
        repo_name = quote(repo["name"], safe="")
        # The response's languages_url is intentionally ignored.
        path = f"/repos/{owner}/{repo_name}/languages"
        counts = _request_json(path, token=token)
        if not isinstance(counts, dict) or any(
            not isinstance(language, str)
            or not language
            or type(byte_count) is not int
            or byte_count < 0
            for language, byte_count in counts.items()
        ):
            raise RuntimeError(f"GitHub API returned invalid language data for {path}.")
        for language, byte_count in counts.items():
            languages[language] = languages.get(language, 0) + byte_count

    return {
        "available": True,
        "profile": profile,
        "repos": repositories,
        "languages": dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": SCOPE,
    }
