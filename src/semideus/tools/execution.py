"""Sandboxed code/command execution."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from semideus.core.errors import ExecutionError

logger = logging.getLogger(__name__)

# Commands that are never allowed
BLOCKED_COMMANDS = frozenset({
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero",
    ":(){:|:&};:",
})

# Maximum execution time in seconds
DEFAULT_TIMEOUT = 30


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    return_code: int

    @property
    def success(self) -> bool:
        return self.return_code == 0

    @property
    def output(self) -> str:
        """Combined output, preferring stdout."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"[stderr] {self.stderr}")
        return "\n".join(parts) if parts else "(no output)"


def _is_blocked(command: str) -> bool:
    """Check if command matches a blocked pattern."""
    normalized = command.strip().lower()
    return any(blocked in normalized for blocked in BLOCKED_COMMANDS)


async def execute_command(
    command: str,
    cwd: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    sandbox: bool = True,
) -> ExecutionResult:
    """Execute a shell command with safety checks.

    Args:
        command: Shell command to execute.
        cwd: Working directory (defaults to current).
        timeout: Maximum execution time in seconds.
        sandbox: If True, apply safety restrictions.

    Returns:
        ExecutionResult with stdout, stderr, and return code.
    """
    if sandbox and _is_blocked(command):
        raise ExecutionError(f"Command blocked by safety rules: {command}")

    work_dir = cwd or os.getcwd()

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
        return ExecutionResult(
            stdout=stdout.decode("utf-8", errors="replace").strip(),
            stderr=stderr.decode("utf-8", errors="replace").strip(),
            return_code=process.returncode or 0,
        )
    except asyncio.TimeoutError:
        process.kill()
        raise ExecutionError(f"Command timed out after {timeout}s: {command}")
    except Exception as e:
        raise ExecutionError(f"Command execution failed: {e}") from e
