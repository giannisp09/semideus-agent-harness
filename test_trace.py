import asyncio
from semideus.core.config import HarnessConfig, TraceConfig, ProviderConfig, ToolsConfig
from semideus.harness.harness import Harness

async def main():
    config = HarnessConfig(
        provider=ProviderConfig(name="anthropic", model="claude-3-haiku-20240307"),
        trace=TraceConfig(enabled=True, path=".semideus/traces"),
        tools=ToolsConfig(enabled=[])
    )
    # We will use mock provider to avoid hitting real APIs
    config.provider.name = "mock"
    harness = Harness(config)
    
    # We need a mock provider class registered
    try:
        from semideus.core.registry import registry
        from semideus.core.types import ComponentType, LLMResponse, StopReason, TokenUsage
        from semideus.core.interfaces import LLMProvider
        
        class MockProvider(LLMProvider):
            def __init__(self, config):
                self.config = config
                
            async def complete(self, messages, tools=None):
                return LLMResponse(
                    content="This is a mock response",
                    tool_calls=[],
                    stop_reason=StopReason.END_TURN,
                    usage=TokenUsage()
                )
            
            async def close(self):
                pass
                
        registry.register(ComponentType.PROVIDER, "mock")(MockProvider)
    except Exception as e:
        print("Mock err:", e)
        
    await harness.run("Do a dummy task")
    await harness.close()

if __name__ == "__main__":
    asyncio.run(main())
