"""GitHub repo-engineering helpers for session-scoped workspaces.

This module powers local clone/edit/commit/push/PR workflows using the user's
connected GitHub PAT. Repositories live inside the current Aegis session
workspace and are cleaned up when the session ends.
"""

from __future__ import annotations

import asyncio
import base64
import os
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import httpx

from backend.session_workspace import get_session_repos_root, resolve_session_path

_GITHUB_API_BASE = "https://api.github.com"
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(slots=True)
class GitHubIdentity:
    """Authenticated GitHub actor metadata."""

    login: str
    name: str
    email: str


class GitHubRepoWorkspaceManager:
    """Manage GitHub API calls plus local git/gh repo workflows."""

    def __init__(self, *, session_id: str, token: str) -> None:
        self.session_id = session_id
        self.token = token.strip()
        self._identity: GitHubIdentity | None = None

    async def ensure_identity(self) -> GitHubIdentity:
        """Fetch and cache the authenticated GitHub user identity."""
        if self._identity is not None:
            return self._identity
        payload = await self.api_request("GET", "/user")
        login = str(payload.get("login", "")).strip()
        if not login:
            raise RuntimeError(payload.get("message") or "Unable to verify the connected GitHub PAT.")
        name = str(payload.get("name") or login).strip() or login
        email = str(payload.get("email") or f"{login}@users.noreply.github.com").strip()
        self._identity = GitHubIdentity(login=login, name=name, email=email)
        return self._identity

    async def api_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a GitHub REST API request with the connected PAT."""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, f"{_GITHUB_API_BASE}{path}", headers=headers, params=params, json=json_body)
        try:
            data = response.json()
        except ValueError:
            data = {"message": response.text}
        if response.status_code >= 400:
            message = data.get("message") if isinstance(data, dict) else response.text
            raise RuntimeError(message or f"GitHub API request failed with HTTP {response.status_code}.")
        return data

    async def list_repos(self, per_page: int = 30) -> dict[str, Any]:
        """List repositories for the authenticated user."""
        payload = await self.api_request("GET", "/user/repos", params={"per_page": min(max(per_page, 1), 100), "sort": "updated"})
        repos = [
            {
                "id": item.get("id"),
                "full_name": item.get("full_name"),
                "default_branch": item.get("default_branch"),
                "private": bool(item.get("private", False)),
                "description": item.get("description") or "",
                "html_url": item.get("html_url"),
                "updated_at": item.get("updated_at"),
            }
            for item in payload if isinstance(item, dict)
        ]
        return {"ok": True, "repos": repos}

    async def get_issues(self, repo: str, state: str = "open") -> dict[str, Any]:
        """List issues for a repository."""
        self._validate_repo_name(repo)
        payload = await self.api_request("GET", f"/repos/{repo}/issues", params={"state": state, "per_page": 30})
        return {"ok": True, "issues": payload}

    async def create_issue(self, repo: str, title: str, body: str = "") -> dict[str, Any]:
        """Create an issue in a repository."""
        self._validate_repo_name(repo)
        if not title.strip():
            raise RuntimeError("title is required")
        payload = await self.api_request("POST", f"/repos/{repo}/issues", json_body={"title": title.strip(), "body": body})
        return {"ok": True, "number": payload.get("number"), "html_url": payload.get("html_url")}

    async def get_pull_requests(self, repo: str, state: str = "open") -> dict[str, Any]:
        """List pull requests for a repository."""
        self._validate_repo_name(repo)
        payload = await self.api_request("GET", f"/repos/{repo}/pulls", params={"state": state, "per_page": 30})
        return {"ok": True, "pull_requests": payload}

    async def create_comment(self, repo: str, issue_number: int, body: str) -> dict[str, Any]:
        """Create an issue or pull-request comment."""
        self._validate_repo_name(repo)
        if not body.strip():
            raise RuntimeError("body is required")
        payload = await self.api_request("POST", f"/repos/{repo}/issues/{issue_number}/comments", json_body={"body": body})
        return {"ok": True, "id": payload.get("id"), "html_url": payload.get("html_url")}

    async def get_file(self, repo: str, path: str, ref: str | None = None) -> dict[str, Any]:
        """Read a file from a remote GitHub repository."""
        self._validate_repo_name(repo)
        if not path.strip():
            raise RuntimeError("path is required")
        params = {"ref": ref} if ref else None
        payload = await self.api_request("GET", f"/repos/{repo}/contents/{path}", params=params)
        content = None
        if isinstance(payload, dict) and payload.get("encoding") == "base64" and payload.get("content"):
            content = base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
        return {
            "ok": True,
            "name": payload.get("name") if isinstance(payload, dict) else None,
            "path": payload.get("path") if isinstance(payload, dict) else path,
            "content": content,
            "size": payload.get("size") if isinstance(payload, dict) else None,
        }

    async def clone_repo(self, repo: str, ref: str | None = None) -> dict[str, Any]:
        """Clone a repository into the current session workspace."""
        self._validate_repo_name(repo)
        repo_root = get_session_repos_root(self.session_id)
        local_path = repo_root / repo.replace("/", "__")
        if local_path.exists():
            if not (local_path / ".git").exists():
                raise RuntimeError("A non-git directory already exists for this repository in the current session workspace.")
            await self._configure_commit_identity(local_path)
            await self._run_git(["fetch", "origin", "--prune"], cwd=local_path, timeout=240)
            if ref:
                await self._run_git(["checkout", ref], cwd=local_path)
            branch = (await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=local_path))["stdout"].strip()
            default_branch = await self._get_default_branch(local_path)
            return {
                "ok": True,
                "repo": repo,
                "local_path": str(local_path),
                "current_branch": branch,
                "default_branch": default_branch,
                "reused_existing_clone": True,
            }

        clone_url = f"https://github.com/{repo}.git"
        await self._run_git(["clone", clone_url, str(local_path)], cwd=repo_root, timeout=240)
        await self._configure_commit_identity(local_path)
        if ref:
            await self._run_git(["checkout", ref], cwd=local_path)
        branch = (await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=local_path))["stdout"].strip()
        default_branch = await self._get_default_branch(local_path)
        return {
            "ok": True,
            "repo": repo,
            "local_path": str(local_path),
            "current_branch": branch,
            "default_branch": default_branch,
            "reused_existing_clone": False,
        }

    async def create_branch(self, local_path: str, branch_name: str, base_ref: str | None = None) -> dict[str, Any]:
        """Create or reset a local branch and switch to it."""
        repo_path = self._resolve_repo_path(local_path)
        if not branch_name.strip():
            raise RuntimeError("branch_name is required")
        if base_ref and base_ref.strip():
            await self._run_git(["checkout", "-B", branch_name.strip(), base_ref.strip()], cwd=repo_path)
        else:
            await self._run_git(["checkout", "-B", branch_name.strip()], cwd=repo_path)
        return {"ok": True, "local_path": str(repo_path), "branch": branch_name.strip()}

    async def repo_status(self, local_path: str) -> dict[str, Any]:
        """Return git status metadata for a local repository clone."""
        repo_path = self._resolve_repo_path(local_path)
        branch = (await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path))["stdout"].strip()
        porcelain = (await self._run_git(["status", "--short"], cwd=repo_path))["stdout"]
        changed_files: list[dict[str, str]] = []
        for line in porcelain.splitlines():
            status = line[:2].strip() or "??"
            file_path = line[3:].strip() if len(line) > 3 else ""
            if file_path:
                changed_files.append({"status": status, "path": file_path})
        status_text = (await self._run_git(["status", "--short", "--branch"], cwd=repo_path))["stdout"]
        return {"ok": True, "local_path": str(repo_path), "branch": branch, "changed_files": changed_files, "status_text": status_text.strip()}

    async def repo_diff(self, local_path: str, staged: bool = False, pathspec: str | None = None) -> dict[str, Any]:
        """Return a unified git diff for the repository."""
        repo_path = self._resolve_repo_path(local_path)
        command = ["diff"]
        if staged:
            command.append("--staged")
        if pathspec and pathspec.strip():
            command.extend(["--", pathspec.strip()])
        diff_text = (await self._run_git(command, cwd=repo_path, timeout=120))['stdout']
        return {"ok": True, "local_path": str(repo_path), "staged": staged, "diff": diff_text}

    async def commit_changes(self, local_path: str, message: str) -> dict[str, Any]:
        """Stage all local changes and create a commit."""
        repo_path = self._resolve_repo_path(local_path)
        if not message.strip():
            raise RuntimeError("message is required")
        await self._configure_commit_identity(repo_path)
        await self._run_git(["add", "-A"], cwd=repo_path)
        status_check = (await self._run_git(["status", "--short"], cwd=repo_path))["stdout"].strip()
        if not status_check:
            raise RuntimeError("No local changes to commit.")
        await self._run_git(["commit", "-m", message.strip()], cwd=repo_path, timeout=120)
        sha = (await self._run_git(["rev-parse", "HEAD"], cwd=repo_path))["stdout"].strip()
        branch = (await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path))["stdout"].strip()
        return {"ok": True, "local_path": str(repo_path), "branch": branch, "commit": sha}

    async def push_branch(self, local_path: str, branch: str | None = None) -> dict[str, Any]:
        """Push the current or selected branch to origin."""
        repo_path = self._resolve_repo_path(local_path)
        current_branch = branch.strip() if branch and branch.strip() else (await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path))["stdout"].strip()
        await self._run_git(["push", "--set-upstream", "origin", current_branch], cwd=repo_path, timeout=240)
        remote = (await self._run_git(["remote", "get-url", "origin"], cwd=repo_path))["stdout"].strip()
        return {"ok": True, "local_path": str(repo_path), "branch": current_branch, "remote": remote}

    async def create_pull_request(
        self,
        local_path: str,
        title: str,
        body: str,
        *,
        base: str = "main",
        head: str | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Open a pull request from the local repository using the GitHub CLI."""
        repo_path = self._resolve_repo_path(local_path)
        if not title.strip():
            raise RuntimeError("title is required")
        head_ref = head.strip() if head and head.strip() else (await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path))["stdout"].strip()
        command = ["gh", "pr", "create", "--title", title.strip(), "--body", body, "--base", base.strip(), "--head", head_ref]
        if draft:
            command.append("--draft")
        result = await self._run_command(command, cwd=repo_path, timeout=240)
        stdout = result["stdout"].strip()
        url = ""
        for token in stdout.split():
            if token.startswith("https://github.com/"):
                url = token
                break
        return {"ok": True, "local_path": str(repo_path), "head": head_ref, "base": base.strip(), "html_url": url or stdout, "raw": stdout}

    async def _get_default_branch(self, repo_path: Path) -> str:
        result = await self._run_git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repo_path)
        ref = result["stdout"].strip()
        return ref.split("/", maxsplit=2)[-1] if ref else "main"

    async def _configure_commit_identity(self, repo_path: Path) -> None:
        identity = await self.ensure_identity()
        await self._run_git(["config", "user.name", identity.name], cwd=repo_path)
        await self._run_git(["config", "user.email", identity.email], cwd=repo_path)

    def _resolve_repo_path(self, local_path: str) -> Path:
        repo_path = resolve_session_path(self.session_id, local_path)
        if not repo_path.exists() or not (repo_path / ".git").exists():
            raise RuntimeError("local_path must point to a cloned repository inside the current session workspace.")
        return repo_path

    async def _run_git(self, args: list[str], *, cwd: Path, timeout: int = 60) -> dict[str, str]:
        return await self._run_command(["git", *args], cwd=cwd, timeout=timeout)

    async def _run_command(self, command: list[str], *, cwd: Path, timeout: int = 60) -> dict[str, str]:
        env = os.environ.copy()
        env.update({
            "GITHUB_TOKEN": self.token,
            "GH_TOKEN": self.token,
            "GIT_ASKPASS": str(self._ensure_askpass_script()),
            "GIT_TERMINAL_PROMPT": "0",
            "GH_CONFIG_DIR": str(self._ensure_gh_config_dir()),
        })
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError(f"Command timed out after {timeout} seconds: {' '.join(command[:3])}") from exc
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        if process.returncode != 0:
            message = stderr_text.strip() or stdout_text.strip() or "Command failed."
            raise RuntimeError(message)
        return {"stdout": stdout_text, "stderr": stderr_text}

    def _ensure_askpass_script(self) -> Path:
        root = get_session_repos_root(self.session_id).parent
        script_path = root / "git_askpass.sh"
        if script_path.exists():
            return script_path
        script_path.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  *Username*) printf '%s\\n' 'x-access-token' ;;\n"
            "  *) printf '%s\\n' \"$GITHUB_TOKEN\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        script_path.chmod(0o700)
        return script_path

    def _ensure_gh_config_dir(self) -> Path:
        path = get_session_repos_root(self.session_id).parent / "gh"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _validate_repo_name(repo: str) -> None:
        if not _REPO_RE.match(repo.strip()):
            raise RuntimeError("repo must be in the form owner/repo")
