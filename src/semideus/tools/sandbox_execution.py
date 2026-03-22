"""Docker Sandbox execution tool."""

from __future__ import annotations

import asyncio
from typing import Any

from semideus.core.interfaces import Tool
from semideus.core.types import ToolDefinition, ToolResult
from semideus.tools.execution import ExecutionResult, ExecutionError

async def execute_sandbox_command(
    command: str,
    sandbox_name: str,
    cwd: str | None = None,
    timeout: float = 30.0,
) -> ExecutionResult:
    """Execute a shell command inside a Docker Sandbox."""
    args = ["sandbox", "exec"]
    if cwd:
        args.extend(["-w", cwd])
    args.extend([sandbox_name, "bash", "-c", command])

    try:
        process = await asyncio.create_subprocess_exec(
            "docker", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
        try:
            process.kill()
        except:
            pass
        raise ExecutionError(f"Command timed out after {timeout}s in sandbox {sandbox_name}: {command}")
    except Exception as e:
        raise ExecutionError(f"Sandbox command execution failed: {e}") from e


class SandboxShellTool(Tool):
    """Execute shell commands inside a Docker Sandbox microVM."""

    def __init__(self, sandbox_name: str):
        self.sandbox_name = sandbox_name

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell",
            description="Execute a shell command inside the secure Docker Sandbox isolated from the host.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (defaults to current inside sandbox, typically same as host).",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds (default 30).",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        command = arguments["command"]
        cwd = arguments.get("cwd")
        timeout = arguments.get("timeout", 120.0)

        # Foolproof fallback: LLMs frequently ignore prompt instructions and try to curl localhost.
        # Since the shell is sandboxed, localhost refers to the sandbox itself.
        # Rewrite to host.docker.internal which resolves to the host where the challenge ports are mapped.
        # NOTE: Docker AI Sandbox proxy blocks `host.docker.internal` natively. We use the host LAN IP.
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(('10.255.255.255', 1))
                host_ip = s.getsockname()[0]
        except Exception:
            host_ip = "host.docker.internal"

        command = command.replace("localhost", host_ip)
        command = command.replace("127.0.0.1", host_ip)
        command = command.replace("host.docker.internal", host_ip)

        try:
            result = await execute_sandbox_command(
                command=command,
                sandbox_name=self.sandbox_name,
                cwd=cwd,
                timeout=timeout
            )
            return ToolResult(
                tool_call_id="",
                content=result.output,
                is_error=not result.success,
            )
        except Exception as e:
            return ToolResult(tool_call_id="", content=str(e), is_error=True)
