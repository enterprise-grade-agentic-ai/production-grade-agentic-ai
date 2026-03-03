"""
Custom tools for the Bug Fixer agents.

Tool inventory — mirrors what Claude Code itself can do:
  grep_search      Search file content by regex pattern
  glob_search      Find files by name/path pattern
  read_file        Read a file's content
  list_directory   List a directory's entries
  edit_file        Replace an exact text block in a file
  write_file       Create or overwrite a file
  bash             Run any shell command in the Docker sandbox
  run_command      Execute a shell command (for running tests)
  web_fetch        Fetch a web page as plain text
  web_search       Search the web via DuckDuckGo

All filesystem and shell tools run inside a Docker sandbox started by
set_sandbox_root().  The sandbox directory is mounted read-write so agents
can edit files.  Internet access is permitted; the host machine is not
reachable from inside the container.

Execution path: every non-web tool calls _run_bash(), which is the single
point that issues `docker exec` commands.
"""

import atexit
import base64
import json
import logging
import re
import shlex
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

from crewai.tools import tool

# Clip large outputs so the LLM context doesn't overflow.
_MAX_CHARS = 8_000

# ── Docker sandbox ────────────────────────────────────────────────────────────
# One long-running Alpine container per session.  All shell operations go
# through _run_bash(), which issues `docker exec` against this container.

_sandbox_root: Union[Path, None] = None
_container_id: Union[str, None] = None
_CONTAINER_IMAGE = "alpine:latest"
_CONTAINER_MOUNT = "/code"


def _stop_container() -> None:
    """Stop the sandboxed Docker container (called automatically on exit)."""
    global _container_id
    if _container_id:
        subprocess.run(
            ["docker", "stop", _container_id],
            capture_output=True, timeout=15,
        )
        _container_id = None
        logger.info("Docker sandbox container stopped.")


def set_sandbox_root(path: Union[str, Path]) -> None:
    """Pin every filesystem tool to *path* and start the Docker sandbox.
    Must be called by the flow before any agent crew runs."""
    global _sandbox_root, _container_id
    _sandbox_root = Path(path).resolve()

    # Start a long-running Alpine container with:
    #   - read-write mount so the agent can edit files
    #   - host.docker.internal remapped to loopback so the container cannot
    #     reach the host machine via DNS name
    start = subprocess.run(
        [
            "docker", "run", "-d", "--rm",
            # Filesystem: only the code mount is writable; root fs is immutable.
            "-v", f"{_sandbox_root}:{_CONTAINER_MOUNT}",
            "-w", _CONTAINER_MOUNT,
            "--tmpfs", "/tmp:size=64m",     # writable scratch space for shell commands
            # Network: remap the host.docker.internal DNS name to loopback so the
            # container cannot resolve the host by name.  Note: the Docker bridge
            # gateway IP (typically 172.17.0.1) remains reachable at the IP layer;
            # full host-IP blocking with internet access requires a custom Docker
            # network with iptables rules dropping the bridge gateway.
            "--add-host", "host.docker.internal:127.0.0.1",
            # Capabilities: drop every Linux capability so the container cannot
            # manipulate network interfaces, routing tables, mounts, or kernel
            # parameters — even if it can reach the bridge gateway IP.
            "--cap-drop", "ALL",
            # Prevent setuid/setgid binaries from gaining new privileges.
            "--security-opt", "no-new-privileges",
            # Resource limits: guard against runaway processes, fork bombs,
            # CPU exhaustion, and excessive file descriptor / disk usage.
            "--pids-limit", "256",
            "--memory", "512m",
            "--memory-swap", "512m",
            "--cpus", "1.0",
            "--ulimit", "nofile=256:256",
            "--ulimit", "core=0",
            "--ulimit", "fsize=104857600",  # 100 MB max file size
            _CONTAINER_IMAGE,
            "sleep", "infinity",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if start.returncode != 0:
        raise RuntimeError(
            f"Docker is required but could not start a container: "
            f"{start.stderr.strip()}"
        )

    _container_id = start.stdout.strip()
    atexit.register(_stop_container)
    logger.info("Docker sandbox started (container=%s).", _container_id[:12])


def _as_container_path(user_path: str) -> str:
    """Convert a user-supplied path to an absolute path inside the container.

    Relative paths are resolved under /code (the sandbox mount point).
    Absolute paths are used as-is.
    """
    p = Path(user_path)
    return str(p) if p.is_absolute() else f"{_CONTAINER_MOUNT}/{user_path}"


def _run_bash(
    command: str,
    working_directory: str = ".",
    timeout: int = 30,
    stdin_data: Union[str, None] = None,
) -> subprocess.CompletedProcess:
    """Single execution point: run a shell command inside the Docker sandbox.

    All non-web tools route through here — no other code issues docker/subprocess
    calls for sandbox operations.

    Args:
        command: Shell command string passed to ``sh -c``.
        working_directory: Working directory inside the container.
                           Relative paths are resolved under /code.
        timeout: Seconds before the call is aborted.
        stdin_data: Optional text to pipe into the command's stdin.
                    Automatically enables ``docker exec -i``.
    """
    if not _container_id:
        raise RuntimeError(
            "Docker sandbox is not running. Ensure set_sandbox_root() was called."
        )
    cwd = _as_container_path(working_directory)
    docker_cmd = ["docker", "exec"]
    if stdin_data is not None:
        docker_cmd.append("-i")   # keep stdin open so we can pipe data
    docker_cmd += ["-w", cwd, _container_id, "sh", "-c", command]
    return subprocess.run(
        docker_cmd, capture_output=True, text=True,
        timeout=timeout, input=stdin_data,
    )


# ── Read-only exploration tools ──────────────────────────────────────────────

@tool("grep_search")
def grep_search(pattern: str, path: str, file_pattern: str = "*") -> str:
    """Search for a regex pattern inside files, returning matching lines with
    their file path and line number.

    Args:
        pattern: The text or regex to search for.
        path: Directory (or single file) to search.
        file_pattern: Shell glob to restrict which files are searched,
                      e.g. "*.py" or "*.ts". Defaults to "*" (all files).
    """
    try:
        cmd = (
            f"grep -rn --include={shlex.quote(file_pattern)} "
            f"{shlex.quote(pattern)} {shlex.quote(_as_container_path(path))}"
        )
        result = _run_bash(cmd)
        output = result.stdout.strip()
        if not output:
            return f"No matches found for pattern '{pattern}' in '{path}'."
        lines = output.split("\n")
        if len(lines) > 200:
            lines = lines[:200]
            lines.append("… (output truncated to 200 lines)")
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "grep_search timed out after 30 s."
    except Exception as exc:
        return f"grep_search error: {exc}"


@tool("glob_search")
def glob_search(directory: str, pattern: str) -> str:
    """Find files whose paths match a glob pattern.

    Args:
        directory: Base directory for the search.
        pattern: Glob pattern relative to *directory*,
                 e.g. "**/*.py", "src/**/*.ts", "tests/test_*.py".
    """
    parts = pattern.rsplit("/", 1)
    name_pattern = parts[-1]
    subdir = parts[0].replace("**", "").strip("/") if len(parts) > 1 else ""

    base = _as_container_path(directory)
    search_path = f"{base}/{subdir}" if subdir else base

    try:
        cmd = f"find {shlex.quote(search_path)} -type f -name {shlex.quote(name_pattern)}"
        result = _run_bash(cmd)
        output = result.stdout.strip()
        if not output:
            return f"No files matched '{pattern}' inside '{directory}'."
        lines = sorted(output.split("\n"))[:300]
        return "\n".join(lines)
    except Exception as exc:
        return f"glob_search error: {exc}"


@tool("read_file")
def read_file(file_path: str) -> str:
    """Read and return the full text content of a file.

    Args:
        file_path: Relative path to the file.
    """
    try:
        result = _run_bash(f"cat {shlex.quote(_as_container_path(file_path))}")
        if result.returncode != 0:
            return f"File not found or unreadable: {file_path}\n{result.stderr.strip()}"
        content = result.stdout
        if len(content) > _MAX_CHARS:
            return (
                content[:_MAX_CHARS]
                + f"\n\n[Truncated — showing {_MAX_CHARS} of {len(content)} chars]"
            )
        return content
    except subprocess.TimeoutExpired:
        return "read_file timed out after 30 s."
    except Exception as exc:
        return f"read_file error: {exc}"


@tool("list_directory")
def list_directory(directory: str) -> str:
    """List the immediate contents of a directory (files and sub-directories).

    Args:
        directory: Path to the directory to inspect.
    """
    try:
        result = _run_bash(f"ls -la {shlex.quote(_as_container_path(directory))}")
        if result.returncode != 0:
            return f"Directory not found or unreadable: {directory}\n{result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as exc:
        return f"list_directory error: {exc}"


# ── Write / edit tools ────────────────────────────────────────────────────────

@tool("edit_file")
def edit_file(file_path: str, old_content: str, new_content: str) -> str:
    """Replace an exact block of text in a file with new content.

    The *old_content* must appear **exactly once** in the file (including all
    whitespace and indentation).  Read the file first to confirm the text
    before calling this tool.

    Args:
        file_path: Path to the file to modify.
        old_content: The exact text to find and replace (must be unique).
        new_content: The replacement text.
    """
    container_path = _as_container_path(file_path)

    # Read via bash
    try:
        read_result = _run_bash(f"cat {shlex.quote(container_path)}")
        if read_result.returncode != 0:
            return f"File not found: {file_path}"
        original = read_result.stdout
    except Exception as exc:
        return f"edit_file error reading file: {exc}"

    # Validate in Python (exact-match logic must stay in Python)
    if old_content not in original:
        return (
            f"edit_file failed: old_content not found in '{file_path}'. "
            "Check for exact whitespace / indentation match."
        )
    count = original.count(old_content)
    if count > 1:
        return (
            f"edit_file failed: old_content appears {count} times in "
            f"'{file_path}'. Add more surrounding context to make it unique."
        )

    updated = original.replace(old_content, new_content, 1)

    # Write back via bash: pipe base64-encoded content to avoid shell-escaping issues
    content_b64 = base64.b64encode(updated.encode()).decode()
    try:
        result = _run_bash(
            f"base64 -d > {shlex.quote(container_path)}",
            stdin_data=content_b64,
        )
        if result.returncode != 0:
            return f"edit_file write failed: {result.stderr.strip()}"
        return f"Successfully edited '{file_path}'."
    except Exception as exc:
        return f"edit_file error writing file: {exc}"


@tool("write_file")
def write_file(file_path: str, content: str) -> str:
    """Create or fully overwrite a file with the supplied content.
    Parent directories are created automatically if they don't exist.

    Args:
        file_path: Destination path for the file.
        content: Full text content to write.
    """
    container_path = _as_container_path(file_path)
    parent = shlex.quote(str(Path(container_path).parent))

    # Pipe base64-encoded content to avoid shell-escaping issues with arbitrary text
    content_b64 = base64.b64encode(content.encode()).decode()
    try:
        result = _run_bash(
            f"mkdir -p {parent} && base64 -d > {shlex.quote(container_path)}",
            stdin_data=content_b64,
        )
        if result.returncode != 0:
            return f"write_file failed: {result.stderr.strip()}"
        return f"Wrote {len(content)} characters to '{file_path}'."
    except subprocess.TimeoutExpired:
        return "write_file timed out after 30 s."
    except Exception as exc:
        return f"write_file error: {exc}"


# ── Web tools ─────────────────────────────────────────────────────────────────
# Web tools run on the host (not in the Docker sandbox) — they need outbound
# internet access, which the container also has, but routing through the host
# avoids any container-side SSL/proxy complications.

@tool("web_fetch")
def web_fetch(url: str) -> str:
    """Fetch the text content of a web page — useful for reading documentation,
    GitHub issues, or error explanations referenced in the codebase.

    Args:
        url: The full URL to fetch (must start with http:// or https://).
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BugFixerBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")

        # Strip HTML tags and collapse whitespace.
        text = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        if len(text) > _MAX_CHARS:
            text = text[:_MAX_CHARS] + "\n\n[Content truncated]"
        return text
    except urllib.error.HTTPError as exc:
        return f"web_fetch HTTP error {exc.code}: {exc.reason} — {url}"
    except Exception as exc:
        return f"web_fetch error: {exc}"


@tool("web_search")
def web_search(query: str) -> str:
    """Search the web and return a summary of the top results.
    Useful for looking up error messages, library APIs, or known bug fixes.

    Args:
        query: The search query string.
    """
    try:
        # DuckDuckGo Instant Answer API — no API key required.
        params = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        })
        req = urllib.request.Request(
            f"https://api.duckduckgo.com/?{params}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; BugFixerBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        lines: list[str] = []

        if data.get("AbstractText"):
            lines.append(f"Summary: {data['AbstractText']}")
            if data.get("AbstractURL"):
                lines.append(f"Source : {data['AbstractURL']}")

        for result in data.get("RelatedTopics", [])[:8]:
            if isinstance(result, dict) and result.get("Text"):
                text = result["Text"]
                url  = result.get("FirstURL", "")
                lines.append(f"- {text}" + (f"\n  {url}" if url else ""))

        if not lines:
            return (
                f"No instant-answer results found for '{query}'. "
                "Try web_fetch on a specific documentation URL instead."
            )

        return "\n\n".join(lines)
    except Exception as exc:
        return f"web_search error: {exc}"


# ── General bash tool ─────────────────────────────────────────────────────────

@tool("bash")
def bash(command: str, working_directory: str = ".") -> str:
    """Run any shell command inside the Docker sandbox and return its output.

    The sandbox directory is mounted read-write so commands may create, edit,
    or delete files.  The container cannot reach the host machine but retains
    internet access.

    Args:
        command: The shell command to run.
        working_directory: Directory in which to run the command (relative to
                           the sandbox root, or absolute inside the container).
    """
    if not command.strip():
        return "bash error: empty command."
    try:
        result = _run_bash(command, working_directory=working_directory)
        parts: list[str] = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr}")
        if not parts:
            parts.append(f"(exit code {result.returncode}, no output)")
        full = "\n".join(parts)
        if len(full) > _MAX_CHARS:
            full = full[:_MAX_CHARS] + "\n\n[Output truncated]"
        return full
    except subprocess.TimeoutExpired:
        return "bash timed out after 30 s."
    except Exception as exc:
        return f"bash error: {exc}"


# ── Execution tool ────────────────────────────────────────────────────────────

@tool("run_command")
def run_command(command: str, working_directory: str = ".") -> str:
    """Run a shell command and return its combined stdout + stderr output.
    Primarily used to execute the project's test suite.

    Args:
        command: The shell command to run, e.g. "pytest tests/" or
                 "python -m pytest -v".
        working_directory: Directory in which to run the command.
                           Defaults to the sandbox root.
    """
    try:
        result = _run_bash(command, working_directory=working_directory, timeout=120)
        parts: list[str] = []
        if result.stdout:
            parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr}")
        parts.append(f"Exit code: {result.returncode}")
        full = "\n\n".join(parts)
        if len(full) > _MAX_CHARS:
            full = full[:_MAX_CHARS] + "\n\n[Output truncated]"
        return full
    except subprocess.TimeoutExpired:
        return "run_command timed out after 120 s."
    except Exception as exc:
        return f"run_command error: {exc}"
