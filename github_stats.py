"""A small GitHub GraphQL client plus the handful of numbers the profile card needs."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

API_URL = "https://api.github.com/graphql"


class GitHubError(RuntimeError):
    """GitHub answered, but not with anything usable."""


class AuthError(GitHubError):
    """Token missing, expired, under-scoped, or rate limited."""


@dataclass
class Stats:
    repos: int | None = None
    contributed: int | None = None
    stars: int | None = None
    commits: int | None = None
    followers: int | None = None
    loc_add: int | None = None
    loc_del: int | None = None

    @property
    def loc_net(self) -> int | None:
        if self.loc_add is None or self.loc_del is None:
            return None
        return self.loc_add - self.loc_del


# --------------------------------------------------------------------------- queries

Q_USER = """
query ($login: String!) {
  user(login: $login) {
    id
    createdAt
    followers(first: 1) { totalCount }
    repositories(first: 1, ownerAffiliations: OWNER) { totalCount }
    contributed: repositoriesContributedTo(
      first: 1
      includeUserRepositories: false
      contributionTypes: [COMMIT, PULL_REQUEST, PULL_REQUEST_REVIEW, ISSUE]
    ) { totalCount }
  }
}
"""

Q_OWNED = """
query ($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
      pageInfo { hasNextPage endCursor }
      nodes { stargazerCount }
    }
  }
}
"""

Q_COMMITS = """
query ($login: String!, $since: DateTime!, $until: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $since, to: $until) { totalCommitContributions }
  }
}
"""

Q_REPOS = """
query ($login: String!, $cursor: String, $aff: [RepositoryAffiliation], $fork: Boolean) {
  user(login: $login) {
    repositories(first: 50, after: $cursor, ownerAffiliations: $aff, isFork: $fork) {
      pageInfo { hasNextPage endCursor }
      nodes { nameWithOwner }
    }
  }
}
"""

Q_COUNT = """
query ($owner: String!, $name: String!, $uid: ID!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit { history(first: 1, author: {id: $uid}) { totalCount } }
      }
    }
  }
}
"""

Q_HISTORY = """
query ($owner: String!, $name: String!, $uid: ID!, $cursor: String, $page: Int!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: $page, after: $cursor, author: {id: $uid}) {
            pageInfo { hasNextPage endCursor }
            nodes { additions deletions }
          }
        }
      }
    }
  }
}
"""


# --------------------------------------------------------------------------- client

class Client:
    def __init__(self, token: str):
        self.http = requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {token}", "User-Agent": "profile-card-builder"})

    def query(self, query: str, **variables) -> dict:
        """POST a GraphQL query and return its `data`; retries network hiccups and 5xx responses."""
        problem = "unknown"
        for attempt in range(4):
            try:
                resp = self.http.post(API_URL, json={"query": query, "variables": variables}, timeout=60)
            except requests.RequestException as exc:
                problem = type(exc).__name__
            else:
                if resp.status_code in (401, 403):
                    raise AuthError(
                        f"HTTP {resp.status_code} from GitHub - check the ACCESS_TOKEN secret, its scopes "
                        "(repo, read:user), that it has not expired, or wait if you hit a rate limit"
                    )
                if resp.status_code == 200:
                    body = resp.json()
                    if body.get("data") is None:
                        raise GitHubError("GraphQL error: " + json.dumps(body.get("errors"))[:300])
                    if body.get("errors"):
                        # a partial answer (say, a field this token may not read): report only the kind and the
                        # field path, never the message, which could name a private repo in a public log
                        kinds = sorted({f"{e.get('type', '?')} at {'.'.join(map(str, e.get('path') or []))}"
                                        for e in body["errors"] if isinstance(e, dict)})
                        print("::warning title=GitHub sent a partial answer::" + "; ".join(kinds)[:300].replace("%", "%25"))
                    return body["data"]
                problem = f"HTTP {resp.status_code}"
            if attempt < 3:
                time.sleep(2 ** attempt)
        raise GitHubError(f"GitHub kept failing ({problem})")


# --------------------------------------------------------------------------- numbers

def total_stars(client, login: str) -> int:
    total, cursor = 0, None
    while True:
        repos = client.query(Q_OWNED, login=login, cursor=cursor)["user"]["repositories"]
        total += sum(node["stargazerCount"] for node in repos["nodes"])
        if not repos["pageInfo"]["hasNextPage"]:
            return total
        cursor = repos["pageInfo"]["endCursor"]


def total_commits(client, login: str, created_at: str) -> int:
    """Commit contributions since the account was created, one calendar year per request (GitHub's limit)."""
    start = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    total = 0
    for year in range(start.year, now.year + 1):
        since = max(start, datetime(year, 1, 1, tzinfo=timezone.utc))
        until = min(now, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
        data = client.query(Q_COMMITS, login=login, since=since.strftime(stamp), until=until.strftime(stamp))
        total += data["user"]["contributionsCollection"]["totalCommitContributions"]
    return total


def repo_names(client, login: str, affiliations, include_forks: bool) -> list[str]:
    names, cursor = [], None
    while True:
        repos = client.query(
            Q_REPOS,
            login=login,
            cursor=cursor,
            aff=list(affiliations),
            fork=None if include_forks else False,
        )["user"]["repositories"]
        names += [node["nameWithOwner"] for node in repos["nodes"]]
        if not repos["pageInfo"]["hasNextPage"]:
            return names
        cursor = repos["pageInfo"]["endCursor"]


def commit_count(client, owner: str, name: str, uid: str) -> int:
    """How many commits on the default branch were authored by this user (cheap: no diff stats)."""
    data = client.query(Q_COUNT, owner=owner, name=name, uid=uid)
    ref = (data.get("repository") or {}).get("defaultBranchRef")
    history = ((ref or {}).get("target") or {}).get("history")
    return history["totalCount"] if history else 0


def scan_history(client, owner: str, name: str, uid: str) -> tuple[int, int]:
    """Sum additions/deletions over the user's commits on the default branch."""
    added = deleted = 0
    cursor, page = None, 100
    while True:
        try:
            data = client.query(Q_HISTORY, owner=owner, name=name, uid=uid, cursor=cursor, page=page)
            ref = (data.get("repository") or {}).get("defaultBranchRef")
            if not ref:  # empty repo
                return 0, 0
            history = ref["target"]["history"]
            nodes = history["nodes"]
        except AuthError:
            raise
        except (GitHubError, KeyError, TypeError):
            if page <= 10:
                raise
            page //= 2  # big pages sometimes time out on GitHub's side; retry with smaller ones
            continue
        for node in nodes:
            added += node["additions"]
            deleted += node["deletions"]
        if not history["pageInfo"]["hasNextPage"]:
            return added, deleted
        cursor = history["pageInfo"]["endCursor"]


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def lines_of_code(client, login: str, uid: str, affiliations, include_forks: bool, cache_path: Path) -> tuple[int, int]:
    """Total (additions, deletions) across the user's own commits.

    Per-repo results are cached under a hash of the repo name, so private repo names never end up in a
    public repo, and a repo is only re-scanned when its commit count changes.
    """
    old = _load_json(cache_path)
    new: dict[str, dict] = {}
    names = repo_names(client, login, affiliations, include_forks)
    added = deleted = 0
    finished = False
    try:
        for i, full in enumerate(names, 1):
            owner, name = full.split("/", 1)
            key = hashlib.sha256(full.lower().encode()).hexdigest()
            commits = commit_count(client, owner, name, uid)
            hit = old.get(key)
            if hit and hit.get("commits") == commits:
                a, d, how = hit["add"], hit["del"], "cached"
            else:
                a, d = scan_history(client, owner, name, uid) if commits else (0, 0)
                how = "scanned"
            new[key] = {"commits": commits, "add": a, "del": d}
            added, deleted = added + a, deleted + d
            # repo names are deliberately not printed: Actions logs of a public repo are public
            print(f"  repo {i}/{len(names)}: {commits} commits ({how})")
        finished = True
    finally:
        keep = new if finished else {**old, **new}  # a failed run still keeps its progress
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(keep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return added, deleted


def fetch_stats(client, login: str, *, affiliations, include_forks: bool, loc_cache: Path,
                previous: Stats | None = None) -> Stats:
    user = client.query(Q_USER, login=login)["user"]
    if user is None:
        raise GitHubError(f"No GitHub user called {login!r}")
    stats = Stats(
        repos=user["repositories"]["totalCount"],
        contributed=user["contributed"]["totalCount"],
        followers=user["followers"]["totalCount"],
    )
    stats.stars = total_stars(client, login)
    stats.commits = total_commits(client, login, user["createdAt"])
    try:
        stats.loc_add, stats.loc_del = lines_of_code(
            client, login, user["id"], affiliations, include_forks, loc_cache
        )
    except AuthError:
        raise
    except Exception as exc:  # noqa: BLE001 - keep the card alive with the last good number
        # type only: the message could contain a private repo name, and Actions logs are public
        print(f"::warning::Lines-of-code step failed ({type(exc).__name__}); keeping the previous value. "
              "Run `python build_card.py` locally to see the full error.")
        if previous:
            stats.loc_add, stats.loc_del = previous.loc_add, previous.loc_del
    return stats
