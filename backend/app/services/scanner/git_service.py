import os
import shutil
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

from app.core.error_handler import (
    AppError,
    ErrorCode,
    ErrorSeverity,
    handle_error,
    with_retry,
)

logger = logging.getLogger(__name__)


class GitService:
    """Git 仓库操作服务"""

    def __init__(self, temp_dir: str = "/tmp/stackpilot_repos"):
        self.temp_dir = temp_dir
        self.active_repos: Dict[str, str] = {}

    @handle_error
    @with_retry(config_name="git")
    def clone(self, git_url: str, target_dir: Optional[str] = None, branch: Optional[str] = None) -> str:
        import subprocess

        if target_dir is None:
            repo_name = git_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
            target_dir = os.path.join(self.temp_dir, repo_name)

        os.makedirs(os.path.dirname(target_dir), exist_ok=True)

        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)

        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([git_url, target_dir])

        clone_start = datetime.now(timezone.utc)
        logger.info("Git clone started: url=%s branch=%s target=%s", git_url, branch or "default", target_dir)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            clone_end = datetime.now(timezone.utc)
            duration_ms = int((clone_end - clone_start).total_seconds() * 1000)
            logger.info("Git clone completed: url=%s duration=%dms returncode=%d stderr=%s",
                        git_url, duration_ms, result.returncode,
                        result.stderr[:200] if result.stderr else "none")

            if result.returncode != 0:
                self._raise_git_error(result.stderr, git_url)
        except subprocess.TimeoutExpired:
            clone_end = datetime.now(timezone.utc)
            duration_ms = int((clone_end - clone_start).total_seconds() * 1000)
            logger.error("Git clone timeout: url=%s duration=%dms", git_url, duration_ms)
            raise AppError(
                code=ErrorCode.TIMEOUT_ERROR,
                message=f"Git clone timeout for {git_url} ({duration_ms}ms)",
                severity=ErrorSeverity.MEDIUM,
                retryable=True,
            )
        except FileNotFoundError:
            logger.error("Git command not found")
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message="git command not found",
                severity=ErrorSeverity.HIGH,
            )

        self.active_repos[git_url] = target_dir
        return target_dir

    @handle_error
    def list_remote_branches(self, git_url: str) -> List[str]:
        import subprocess

        logger.info("Listing remote branches: url=%s", git_url)
        start = datetime.now(timezone.utc)
        result = subprocess.run(
            ["git", "ls-remote", "--heads", git_url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        if result.returncode != 0:
            logger.error("List remote branches failed: url=%s duration=%dms stderr=%s",
                         git_url, duration_ms, result.stderr[:200])
            self._raise_git_error(result.stderr, git_url)
        logger.info("List remote branches completed: url=%s duration=%dms branches=%d",
                     git_url, duration_ms, len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0)

        branches = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("\t")
                if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                    branch = parts[1].replace("refs/heads/", "")
                    branches.append(branch)

        return sorted(branches)

    @handle_error
    def get_branches(self, repo_dir: str) -> List[str]:
        import subprocess

        result = subprocess.run(
            ["git", "branch", "-a"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise AppError(
                code=ErrorCode.GIT_ERROR,
                message=f"Failed to get branches: {result.stderr}",
                severity=ErrorSeverity.MEDIUM,
            )

        branches = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("*"):
                branch = line.replace("remotes/origin/", "").strip()
                if branch and branch != "HEAD":
                    branches.append(branch)
            elif line.startswith("* "):
                branches.append(line[2:].strip())

        return list(set(branches))

    @handle_error
    def get_latest_commit(self, repo_dir: str) -> Dict[str, str]:
        import subprocess

        result = subprocess.run(
            ["git", "log", "-1", "--format=%H%n%an%n%ae%n%ci%n%s"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise AppError(
                code=ErrorCode.GIT_ERROR,
                message=f"Failed to get commit info: {result.stderr}",
                severity=ErrorSeverity.MEDIUM,
            )

        lines = result.stdout.strip().split("\n")
        if len(lines) < 5:
            raise AppError(
                code=ErrorCode.GIT_ERROR,
                message="Invalid commit info format",
                severity=ErrorSeverity.LOW,
            )

        return {
            "hash": lines[0],
            "author_name": lines[1],
            "author_email": lines[2],
            "date": lines[3],
            "message": lines[4],
        }

    @handle_error
    def checkout_branch(self, repo_dir: str, branch: str) -> None:
        import subprocess

        result = subprocess.run(
            ["git", "checkout", "-b", branch, f"origin/{branch}"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # 尝试直接 checkout（本地已存在分支）
            result = subprocess.run(
                ["git", "checkout", branch],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise AppError(
                    code=ErrorCode.GIT_ERROR,
                    message=f"Failed to checkout branch {branch}: {result.stderr}",
                    severity=ErrorSeverity.MEDIUM,
                )

    def cleanup(self, git_url: str) -> None:
        repo_dir = self.active_repos.get(git_url)
        if repo_dir and os.path.exists(repo_dir):
            try:
                shutil.rmtree(repo_dir)
                del self.active_repos[git_url]
            except Exception as e:
                logger.warning("Failed to cleanup repo %s: %s", repo_dir, e)

    def _raise_git_error(self, error_msg: str, git_url: str) -> None:
        error_lower = error_msg.lower()

        if "authentication" in error_lower or "credential" in error_lower or "permission" in error_lower:
            raise AppError(
                code=ErrorCode.AUTH_ERROR,
                message=f"Authentication failed for {git_url}: {error_msg}",
                severity=ErrorSeverity.HIGH,
                retryable=False,
            )
        elif "not found" in error_lower or "repository not found" in error_lower:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message=f"Repository not found: {git_url}",
                severity=ErrorSeverity.HIGH,
                retryable=False,
            )
        elif "timeout" in error_lower or "timed out" in error_lower:
            raise AppError(
                code=ErrorCode.TIMEOUT_ERROR,
                message=f"Git operation timeout for {git_url}",
                severity=ErrorSeverity.MEDIUM,
                retryable=True,
            )
        elif "network" in error_lower or "connection" in error_lower:
            raise AppError(
                code=ErrorCode.NETWORK_ERROR,
                message=f"Network error cloning {git_url}: {error_msg}",
                severity=ErrorSeverity.MEDIUM,
                retryable=True,
            )
        else:
            raise AppError(
                code=ErrorCode.GIT_ERROR,
                message=f"Git error for {git_url}: {error_msg}",
                severity=ErrorSeverity.MEDIUM,
                retryable=True,
            )
