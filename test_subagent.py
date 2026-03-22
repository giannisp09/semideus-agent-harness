import asyncio
from unittest.mock import AsyncMock, patch
from semideus.core.config import HarnessConfig, ProviderConfig, ToolsConfig
from semideus.core.types import LLMResponse, StopReason
from semideus.tools.builtin.subagent import SubAgentTool

async def test_subagent_tool():
    config = HarnessConfig(
        provider=ProviderConfig(name="mock"),
        tools=ToolsConfig(enabled=["filesystem", "shell", "git", "web", "subagent"]),
        trace={"enabled": True, "path": ".semideus/traces"}
    )
    
    tool = SubAgentTool(config)
    
    # We will mock harness.run to return a simple string after a small delay
    async def mock_run(task: str):
        await asyncio.sleep(0.1)
        return f"Mock output for {task}"
        
    async def mock_close():
        pass

    with patch("semideus.harness.harness.Harness", autospec=True) as MockHarness:
        instance = MockHarness.return_value
        instance.run = AsyncMock(side_effect=mock_run)
        instance.close = AsyncMock(side_effect=mock_close)
        
        # In executing the subagent tool, Harness() is called inside run_subagent
        result = await tool.execute({"tasks": ["task 1", "task 2"]})
        
        print("Test Result:")
        print(result.content)
        
        assert "Mock output for task 1" in result.content
        assert "Mock output for task 2" in result.content
        assert not result.is_error
        print("Success!")

if __name__ == "__main__":
    asyncio.run(test_subagent_tool())
