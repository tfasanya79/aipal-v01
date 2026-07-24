#!/usr/bin/env python3
"""Sync docs/PRODUCT.md backlog items to GitHub Issues + Projects v2 (AiPal Roadmap)."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_MD = ROOT / "docs" / "PRODUCT.md"
PUBSPEC = ROOT / "apps/mobile" / "pubspec.yaml"
PROJECT_JSON = ROOT / ".github" / "project.json"
SYNC_MARKER = "<!-- aipal-sync-id:"
TRACK_LABEL = "track:backlog"

STATUS_OPTIONS = ["Todo", "In progress", "Done", "Deferred"]
PHASE_OPTIONS = ["A", "B", "C0", "C1", "C2", "C3a", "C3b", "C4"]
AREA_OPTIONS = ["mobile", "api", "docs", "infra"]

AREA_KEYWORDS: list[tuple[str, list[str]]] = [
    ("api", ["turn.py", "plan_extractor", "mem0", "/daily", "ws_session", "fastapi", "pytest", "router"]),
    ("infra", ["ansible", "deploy", "caddy", "play internal", "fastlane", "script"]),
    ("docs", ["doc", "skill", "product.md", "roadmap", "decision"]),
    ("mobile", ["flutter", "wake", "companion", "android", "ios", "notification", "open_wake", "settings"]),
]


@dataclass
class BacklogItem:
    sync_id: str
    phase: str
    title: str
    done: bool
    deferred: bool
    area: str

    @property
    def status(self) -> str:
        if self.done:
            return "Done"
        if self.deferred:
            return "Deferred"
        return "Todo"

    @property
    def issue_title(self) -> str:
        return f"[{self.phase}] {self.title}"


class GitHubGraphQL:
    def __init__(self, token: str) -> None:
        self.token = token

    def query(self, query: str, variables: dict | None = None) -> dict:
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "aipal-project-sync",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            raise RuntimeError(f"GraphQL HTTP {exc.code}: {detail}") from exc
        if body.get("errors"):
            raise RuntimeError(f"GraphQL errors: {body['errors']}")
        return body["data"]


def resolve_token() -> str:
    for key in ("PROJECT_SYNC_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        val = os.environ.get(key)
        if val:
            return val
    try:
        out = subprocess.check_output(["gh", "auth", "token"], stderr=subprocess.DEVNULL, text=True)
        token = out.strip()
        if token:
            return token
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    raise SystemExit(
        "No GitHub token. Set GITHUB_TOKEN/GH_TOKEN or run `gh auth login`."
    )


def slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "item"


def infer_area(text: str) -> str:
    lower = text.lower()
    for area, keys in AREA_KEYWORDS:
        if any(k in lower for k in keys):
            return area
    return "mobile"


def parse_version() -> str:
    if not PUBSPEC.exists():
        return "unknown"
    for line in PUBSPEC.read_text().splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def parse_product_md() -> list[BacklogItem]:
    text = PRODUCT_MD.read_text()
    items: list[BacklogItem] = []
    phase = "A"
    section_phase_map = {
        "phase a backlog": "A",
        "phase b backlog": "B",
        "phase c backlog": "C",
    }

    for raw_line in text.splitlines():
        line = raw_line.strip()
        header = line.lower()
        if line.startswith("## "):
            key = header[3:].strip()
            phase = section_phase_map.get(key, phase)
            continue
        if line.startswith("### "):
            m = re.match(r"###\s+(C\d+a|C\d+b|C4\+?|C0|C1|C2)\s+—", line, re.I)
            if m:
                p = m.group(1).upper()
                if p.startswith("C4"):
                    phase = "C4"
                elif p == "C3A":
                    phase = "C3a"
                elif p == "C3B":
                    phase = "C3b"
                else:
                    phase = p
            continue

        m = re.match(r"^- \[(x| )\]\s+(.+)$", line, re.I)
        if not m:
            continue
        done = m.group(1).lower() == "x"
        body = m.group(2).strip()
        if body.startswith("A") and "—" in body[:4]:
            item_phase = "A"
            title = body.split("—", 1)[1].strip() if "—" in body else body
            prefix = body.split("—", 1)[0].strip()
            sync_id = slugify(prefix)
        elif body.startswith("B") and "—" in body[:5]:
            item_phase = "B"
            title = body.split("—", 1)[1].strip()
            prefix = body.split("—", 1)[0].strip()
            sync_id = slugify(prefix)
        else:
            item_phase = phase if phase != "C" else "C0"
            title = body
            sync_id = slugify(f"{item_phase}-{title}")

        deferred = "deferred" in body.lower() and not done
        items.append(
            BacklogItem(
                sync_id=sync_id,
                phase=item_phase,
                title=title,
                done=done,
                deferred=deferred,
                area=infer_area(body),
            )
        )
    return items


def load_config() -> dict:
    if PROJECT_JSON.exists():
        return json.loads(PROJECT_JSON.read_text())
    return {
        "owner": os.environ.get("GITHUB_REPOSITORY", "tfasanya79/aipal").split("/")[0]
        if "/" in os.environ.get("GITHUB_REPOSITORY", "")
        else "tfasanya79",
        "repo": os.environ.get("GITHUB_REPOSITORY", "tfasanya79/aipal").split("/")[-1]
        if "/" in os.environ.get("GITHUB_REPOSITORY", "")
        else "aipal",
        "project_title": "AiPal Roadmap",
        "project_number": None,
    }


def save_config(cfg: dict) -> None:
    PROJECT_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_JSON.write_text(json.dumps(cfg, indent=2) + "\n")



def get_owner_id(gh: GitHubGraphQL, owner: str) -> str:
    data = gh.query("query($login:String!){user(login:$login){id}}", {"login": owner})
    node = data.get("user")
    if not node:
        raise RuntimeError(f"User not found: {owner}")
    return node["id"]


def get_repo(gh: GitHubGraphQL, owner: str, repo: str) -> dict:
    data = gh.query(
        """
        query($owner:String!,$name:String!){
          repository(owner:$owner,name:$name){ id name }
        }
        """,
        {"owner": owner, "name": repo},
    )
    repository = data.get("repository")
    if not repository:
        raise RuntimeError(f"Repository not found: {owner}/{repo}")
    return repository


def find_project(gh: GitHubGraphQL, owner: str, title: str) -> dict | None:
    """Find user-owned project (PAT + project scope — GitHub-documented path)."""
    data = gh.query(
        """
        query($login:String!){
          user(login:$login){
            projectsV2(first:50){ nodes { id number title url } }
          }
        }
        """,
        {"login": owner},
    )
    user = data.get("user")
    if not user:
        return None
    for node in user["projectsV2"]["nodes"]:
        if node["title"] == title:
            return node
    return None


def create_project(gh: GitHubGraphQL, owner: str, title: str) -> dict:
    owner_id = get_owner_id(gh, owner)
    data = gh.query(
        """
        mutation($ownerId:ID!,$title:String!){
          createProjectV2(input:{ownerId:$ownerId,title:$title}){
            projectV2{ id number title url }
          }
        }
        """,
        {"ownerId": owner_id, "title": title},
    )
    return data["createProjectV2"]["projectV2"]


def link_project_to_repo(gh: GitHubGraphQL, project_id: str, repo_id: str) -> None:
    gh.query(
        """
        mutation($projectId:ID!,$repositoryId:ID!){
          linkProjectV2ToRepository(input:{projectId:$projectId,repositoryId:$repositoryId}){
            clientMutationId
          }
        }
        """,
        {"projectId": project_id, "repositoryId": repo_id},
    )


def get_project_fields(gh: GitHubGraphQL, owner: str, number: int) -> dict:
    data = gh.query(
        """
        query($login:String!,$number:Int!){
          user(login:$login){
            projectV2(number:$number){
              id
              number
              title
              url
              fields(first:30){
                nodes{
                  ... on ProjectV2FieldCommon { id name }
                  ... on ProjectV2SingleSelectField {
                    id name options { id name }
                  }
                }
              }
            }
          }
        }
        """,
        {"login": owner, "number": number},
    )
    project = data["user"]["projectV2"]
    if not project:
        raise RuntimeError(f"Project #{number} not found for user {owner}")
    return project


def ensure_single_select_field(
    gh: GitHubGraphQL, project_id: str, name: str, options: list[str], existing: dict
) -> dict:
    if name in existing:
        return existing[name]
    option_inputs = [{"name": opt, "color": "GRAY"} for opt in options]
    try:
        data = gh.query(
            """
            mutation($projectId:ID!,$name:String!,$options:[ProjectV2SingleSelectFieldOptionInput!]!){
              createProjectV2Field(input:{
                projectId:$projectId, dataType:SINGLE_SELECT, name:$name,
                singleSelectOptions:$options
              }){
                projectV2Field{
                  ... on ProjectV2SingleSelectField { id name options { id name } }
                }
              }
            }
            """,
            {"projectId": project_id, "name": name, "options": option_inputs},
        )
        field = data["createProjectV2Field"]["projectV2Field"]
        return {"id": field["id"], "options": {o["name"]: o["id"] for o in field["options"]}}
    except RuntimeError as exc:
        if "already exists" in str(exc).lower() or "name" in str(exc).lower():
            return existing.get(name, {"id": "", "options": {}})
        raise


def parse_fields(nodes: list) -> dict:
    out: dict = {}
    for node in nodes:
        if "options" in node:
            out[node["name"]] = {
                "id": node["id"],
                "options": {o["name"]: o["id"] for o in node["options"]},
            }
    return out


def ensure_labels(gh: GitHubGraphQL, repo_id: str) -> None:
    labels = [TRACK_LABEL] + [f"phase:{p}" for p in PHASE_OPTIONS] + [f"area:{a}" for a in AREA_OPTIONS]
    for name in labels:
        color = "ededed" if name == TRACK_LABEL else "1d76db"
        try:
            gh.query(
                """
                mutation($repoId:ID!,$name:String!,$color:String!){
                  createLabel(input:{repositoryId:$repoId,name:$name,color:$color}){
                    label{ name }
                  }
                }
                """,
                {"repoId": repo_id, "name": name, "color": color},
            )
        except RuntimeError:
            # Label may already exist or token lacks label scope — non-fatal.
            pass


def fetch_tracked_issues(gh: GitHubGraphQL, owner: str, repo: str) -> dict[str, dict]:
    data = gh.query(
        """
        query($owner:String!,$name:String!){
          repository(owner:$owner,name:$name){
            issues(first:100, states:[OPEN,CLOSED]){
              nodes{ id number title body state projectItems(first:5){
                nodes{ id project{id number} }
              }}
            }
          }
        }
        """,
        {"owner": owner, "name": repo},
    )
    by_sync: dict[str, dict] = {}
    for issue in data["repository"]["issues"]["nodes"]:
        body = issue.get("body") or ""
        if SYNC_MARKER not in body:
            continue
        for line in body.splitlines():
            if line.strip().startswith(SYNC_MARKER):
                sync_id = line.split(":", 1)[1].strip().rstrip("-->").strip()
                by_sync[sync_id] = issue
                break
    return by_sync


def create_issue(
    gh: GitHubGraphQL, repo_id: str, owner: str, repo: str, item: BacklogItem, version: str
) -> dict:
    body = (
        f"{SYNC_MARKER} {item.sync_id} -->\n\n"
        f"**Phase:** {item.phase}\n"
        f"**Area:** {item.area}\n"
        f"**App version (sync):** {version}\n\n"
        f"Canonical source: `docs/PRODUCT.md` (auto-synced).\n"
    )
    data = gh.query(
        """
        mutation($repoId:ID!,$title:String!,$body:String!){
          createIssue(input:{repositoryId:$repoId,title:$title,body:$body}){
            issue{ id number title state }
          }
        }
        """,
        {"repoId": repo_id, "title": item.issue_title, "body": body},
    )
    issue = data["createIssue"]["issue"]
    add_labels_to_issue(
        owner,
        repo,
        issue["number"],
        [TRACK_LABEL, f"phase:{item.phase}", f"area:{item.area}"],
    )
    return issue


def add_labels_to_issue(owner: str, repo: str, issue_number: int, labels: list[str]) -> None:
    """Add labels via REST (simpler than resolving label node IDs)."""
    token = resolve_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/labels"
    payload = json.dumps(labels).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "aipal-project-sync",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code != 422:
            raise


def set_issue_state(gh: GitHubGraphQL, issue_id: str, done: bool) -> None:
    mutation = "closeIssue" if done else "reopenIssue"
    gh.query(
        f"""
        mutation($id:ID!){{{mutation}(input:{{issueId:$id}}){{issue{{state}}}}}}
        """,
        {"id": issue_id},
    )


def add_to_project(gh: GitHubGraphQL, project_id: str, content_id: str) -> str:
    data = gh.query(
        """
        mutation($projectId:ID!,$contentId:ID!){
          addProjectV2ItemById(input:{projectId:$projectId,contentId:$contentId}){
            item{ id }
          }
        }
        """,
        {"projectId": project_id, "contentId": content_id},
    )
    return data["addProjectV2ItemById"]["item"]["id"]


def find_project_item_id(issue: dict, project_number: int) -> str | None:
    for node in issue.get("projectItems", {}).get("nodes", []):
        proj = node.get("project") or {}
        if proj.get("number") == project_number:
            return node["id"]
    return None


def resolve_option_id(options: dict[str, str], value: str) -> str | None:
    if value in options:
        return options[value]
    aliases = {"In progress": "In Progress"}
    if value in aliases and aliases[value] in options:
        return options[aliases[value]]
    lower = {k.lower(): v for k, v in options.items()}
    return lower.get(value.lower())


def update_project_fields(
    gh: GitHubGraphQL,
    project_id: str,
    item_id: str,
    fields: dict,
    status: str,
    phase: str,
    area: str,
) -> None:
    updates = [
        ("Status", status),
        ("Phase", phase),
        ("Area", area),
    ]
    for field_name, value in updates:
        field = fields.get(field_name)
        if not field:
            continue
        option_id = resolve_option_id(field["options"], value)
        if not option_id:
            continue
        gh.query(
            """
            mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,$optionId:String!){
              updateProjectV2ItemFieldValue(input:{
                projectId:$projectId, itemId:$itemId, fieldId:$fieldId,
                value:{ singleSelectOptionId:$optionId }
              }){ clientMutationId }
            }
            """,
            {
                "projectId": project_id,
                "itemId": item_id,
                "fieldId": field["id"],
                "optionId": option_id,
            },
        )


def bootstrap(gh: GitHubGraphQL, cfg: dict, bootstrap_flag: bool) -> dict:
    owner = cfg["owner"]
    repo = cfg["repo"]
    title = cfg.get("project_title", "AiPal Roadmap")
    project = None
    if cfg.get("project_number"):
        try:
            project = get_project_fields(gh, owner, int(cfg["project_number"]))
        except RuntimeError:
            project = None
    if project is None:
        found = find_project(gh, owner, title)
        if found:
            project = get_project_fields(gh, owner, found["number"])
        elif bootstrap_flag:
            created = create_project(gh, owner, title)
            repository = get_repo(gh, owner, repo)
            link_project_to_repo(gh, created["id"], repository["id"])
            project = get_project_fields(gh, owner, created["number"])
            cfg["project_number"] = project["number"]
            cfg["project_url"] = project["url"]
        elif cfg.get("project_number"):
            project = get_project_fields(gh, owner, int(cfg["project_number"]))
        else:
            raise SystemExit(
                f"Project '{title}' not found for {owner}. "
                "Run with --bootstrap or scripts/sync-github-project.sh --bootstrap."
            )

    project_id = project["id"]
    cfg["project_number"] = project["number"]
    cfg["project_url"] = project["url"]
    cfg["project_id"] = project_id

    existing_fields = parse_fields(project["fields"]["nodes"])
    # Use built-in Status field; only create Phase + Area custom fields.
    for name, options in [
        ("Phase", PHASE_OPTIONS),
        ("Area", AREA_OPTIONS),
    ]:
        existing_fields[name] = ensure_single_select_field(
            gh, project_id, name, options, existing_fields
        )

    cfg["fields"] = {
        k: {"id": v["id"], "options": v["options"]} for k, v in existing_fields.items()
    }
    repository = get_repo(gh, owner, repo)
    ensure_labels(gh, repository["id"])
    cfg["bootstrapped"] = True
    save_config(cfg)
    return cfg


def sync_items(gh: GitHubGraphQL, cfg: dict, items: list[BacklogItem], version: str) -> dict:
    owner = cfg["owner"]
    repo = cfg["repo"]
    project_id = cfg["project_id"]
    project_number = int(cfg["project_number"])
    fields = cfg.get("fields") or parse_fields(
        get_project_fields(gh, owner, project_number)["fields"]["nodes"]
    )
    repository = get_repo(gh, owner, repo)
    existing = fetch_tracked_issues(gh, owner, repo)

    stats = {"created": 0, "updated": 0, "done": 0, "todo": 0, "deferred": 0}
    for item in items:
        issue = existing.get(item.sync_id)
        if not issue:
            created = create_issue(gh, repository["id"], owner, repo, item, version)
            issue = {
                "id": created["id"],
                "number": created["number"],
                "state": "OPEN",
                "projectItems": {"nodes": []},
            }
            existing[item.sync_id] = issue
            stats["created"] += 1

        want_closed = item.done
        is_closed = issue["state"] == "CLOSED"
        if want_closed and not is_closed:
            set_issue_state(gh, issue["id"], True)
        elif not want_closed and is_closed and not item.deferred:
            set_issue_state(gh, issue["id"], False)

        item_id = find_project_item_id(issue, project_number)
        if not item_id:
            item_id = add_to_project(gh, project_id, issue["id"])

        update_project_fields(
            gh, project_id, item_id, fields, item.status, item.phase, item.area
        )
        stats["updated"] += 1
        if item.status == "Done":
            stats["done"] += 1
        elif item.status == "Deferred":
            stats["deferred"] += 1
        else:
            stats["todo"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync PRODUCT.md to GitHub Project")
    parser.add_argument("--bootstrap", action="store_true", help="Create project/fields if missing")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no API calls")
    args = parser.parse_args()

    if not PRODUCT_MD.exists():
        raise SystemExit(f"Missing {PRODUCT_MD}")

    items = parse_product_md()
    version = parse_version()
    print(f"Parsed {len(items)} backlog items from PRODUCT.md (app {version})")

    if args.dry_run:
        for item in items[:5]:
            print(f"  {item.sync_id}: {item.status} [{item.phase}] {item.title[:50]}")
        print("  ...")
        return

    token = resolve_token()
    gh = GitHubGraphQL(token)
    cfg = load_config()
    cfg = bootstrap(gh, cfg, bootstrap_flag=args.bootstrap or not cfg.get("bootstrapped"))
    stats = sync_items(gh, cfg, items, version)
    save_config(cfg)

    print(f"Project: {cfg.get('project_url', 'n/a')}")
    print(
        f"Sync complete: created={stats['created']} updated={stats['updated']} "
        f"done={stats['done']} todo={stats['todo']} deferred={stats['deferred']}"
    )


if __name__ == "__main__":
    main()
