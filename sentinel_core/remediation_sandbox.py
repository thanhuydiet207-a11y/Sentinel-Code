"""Temporary-workspace validation runner; not an OS security boundary."""
from __future__ import annotations
import os, shutil, subprocess, tempfile
from pathlib import Path, PurePosixPath

ALLOWED = {"python", "python3", "pytest", "semgrep", "gitleaks", "trivy"}
EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}

class SandboxValidationError(ValueError):
    pass

def run_remediation_sandbox(root, candidate_path, candidate_content, commands, timeout_seconds=120):
    if not isinstance(candidate_path, str) or not candidate_path or chr(92) in candidate_path:
        raise SandboxValidationError("candidate path must be a POSIX relative path")
    path = PurePosixPath(candidate_path)
    if path.is_absolute() or any(p in ("", ".", "..") for p in path.parts):
        raise SandboxValidationError("unsafe candidate path")
    if any(p.startswith(".env") or "secret" in p.lower() or "credential" in p.lower() for p in path.parts):
        raise SandboxValidationError("candidate path targets secret-like material")
    if not isinstance(candidate_content, str) or chr(0) in candidate_content:
        raise SandboxValidationError("candidate must be text without NUL bytes")
    if not isinstance(commands, list) or not commands or len(commands) > 20:
        raise SandboxValidationError("provide 1..20 command argv arrays")
    validated = []
    for command in commands:
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
            raise SandboxValidationError("commands must be non-empty argv arrays")
        if Path(command[0]).name not in ALLOWED:
            raise SandboxValidationError("command executable is not allowlisted")
        if any(x in command for x in (";", "&&", "||", "|", ">", "<", chr(96))):
            raise SandboxValidationError("shell operators are not accepted")
        validated.append(command)
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 600:
        raise SandboxValidationError("timeout must be between 1 and 600 seconds")
    root = Path(root).resolve(strict=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="sentinel-remediation-") as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        for current, dirs, files in os.walk(root, followlinks=False):
            cur = Path(current)
            rel = cur.relative_to(root)
            dirs[:] = [d for d in dirs if d not in EXCLUDED and not d.startswith(".") and not (cur / d).is_symlink()]
            target_dir = workspace / rel
            target_dir.mkdir(parents=True, exist_ok=True)
            for name in files:
                source = cur / name
                if source.is_symlink() or name.startswith(".env") or any(x in name.lower() for x in ("secret", "credential", "token")):
                    continue
                try:
                    shutil.copy2(source, target_dir / name)
                except OSError:
                    pass
        target = workspace.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(candidate_content, encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(workspace / ".home"),
               "PYTHONPATH": str(workspace), "PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"}
        Path(env["HOME"]).mkdir()
        status = "pass"
        for index, command in enumerate(validated):
            try:
                run = subprocess.run(command, cwd=workspace, env=env, shell=False, capture_output=True,
                                    text=True, timeout=timeout_seconds, check=False)
                item = {"index": index, "command": command, "status": "pass" if run.returncode == 0 else "fail",
                        "returncode": run.returncode, "stdout": run.stdout[-20000:], "stderr": run.stderr[-20000:]}
            except subprocess.TimeoutExpired as exc:
                item = {"index": index, "command": command, "status": "timeout", "returncode": None,
                        "stdout": str(exc.stdout or "")[-20000:], "stderr": str(exc.stderr or "")[-20000:]}
            results.append(item)
            if item["status"] != "pass":
                status = "fail"
                break
    return {"status": status, "candidate_path": str(path), "workspace_is_temporary": True,
            "original_repository_modified": False, "os_level_isolation": False,
            "commands": results, "review_required": True}
