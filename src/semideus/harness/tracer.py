"""Agent Trace Logger."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from semideus.core.config import TraceConfig
from semideus.core.events import EventBus

logger = logging.getLogger(__name__)


class AgentTracer:
    """Listens to agent events and outputs rich console traces and JSONL logs."""

    def __init__(self, config: TraceConfig, event_bus: EventBus) -> None:
        self._config = config
        self._event_bus = event_bus
        self._console = Console()
        self._trace_file: Path | None = None
        
        self._register_handlers()
        
    def _register_handlers(self) -> None:
        self._event_bus.subscribe("session.start", self._on_session_start)
        self._event_bus.subscribe("agent.step.before", self._on_step_before)
        self._event_bus.subscribe("agent.step.after", self._on_step_after)
        self._event_bus.subscribe("tool.call.before", self._on_tool_call_before)
        self._event_bus.subscribe("tool.call.after", self._on_tool_call_after)
        self._event_bus.subscribe("session.end", self._on_session_end)

    def _persist(self, event_type: str, data: dict[str, Any]) -> None:
        if not self._trace_file:
            return
            
        record = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "data": data,
        }
        try:
            with open(self._trace_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error("Failed to persist trace event '%s': %s", event_type, e)

    async def _on_session_start(self, data: dict[str, Any]) -> None:
        session_id = data.get("session_id", "unknown")
        
        # Setup persistence file
        if self._config.enabled:
            trace_dir = Path(self._config.path)
            trace_dir.mkdir(parents=True, exist_ok=True)
            self._trace_file = trace_dir / f"{session_id}.jsonl"
            
        self._persist("session.start", data)
        self._console.print(Panel(
            Text(data.get("task", ""), style="bold green"),
            title=f"🚀 Session Start ({session_id})",
            border_style="green"
        ))

    async def _on_step_before(self, data: dict[str, Any]) -> None:
        self._persist("agent.step.before", data)
        step = data.get("step", 0)
        self._console.print(f"\n[bold blue]➡️ Agent Step {step}[/bold blue] (thinking...)")

    async def _on_step_after(self, data: dict[str, Any]) -> None:
        self._persist("agent.step.after", data)
        step = data.get("step", 0)
        reason = data.get("stop_reason", "unknown")
        has_tools = data.get("has_tool_calls", False)
        
        style = "cyan" if has_tools else "magenta"
        msg = f"[bold {style}]ℹ️ Step {step} completed[/bold {style}] (stop_reason: {reason}, tools: {has_tools})"
        self._console.print(msg)

    async def _on_tool_call_before(self, data: dict[str, Any]) -> None:
        self._persist("tool.call.before", data)
        name = data.get("name", "unknown")
        args = data.get("arguments", {})
        
        try:
            args_str = json.dumps(args, indent=2)
        except Exception:
            args_str = str(args)
            
        self._console.print(Panel(
            args_str,
            title=f"🛠️ Tool Call: {name}",
            border_style="yellow",
            subtitle="Executing...",
            subtitle_align="left"
        ))

    async def _on_tool_call_after(self, data: dict[str, Any]) -> None:
        # Avoid dumping huge output structures in the rich console if they are massive
        self._persist("tool.call.after", data)
        name = data.get("name", "unknown")
        result = data.get("result", "")
        is_error = data.get("is_error", False)
        
        if is_error:
            style = "bold red"
            title = f"❌ Tool Error: {name}"
        else:
            style = "dim"
            title = f"✅ Tool Result: {name}"
            
        # Truncate content for console display
        res_str = str(result)
        if len(res_str) > 1000:
            res_str = res_str[:1000] + "\n... [truncated]"
            
        self._console.print(Panel(
            Text(res_str, style=style),
            title=title,
            border_style="red" if is_error else "dim green"
        ))

    async def _on_session_end(self, data: dict[str, Any]) -> None:
        self._persist("session.end", data)
        status = data.get("status", "unknown")
        steps = data.get("steps", 0)
        
        style = "bold green" if status == "completed" else "bold red"
        self._console.print(Panel(
            f"Status: {status}\nSteps: {steps}\nUsage: {data.get('usage', {})}",
            title="🏁 Session End",
            border_style=style
        ))
