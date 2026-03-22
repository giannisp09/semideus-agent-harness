"""Self-evolution loop — recursive feedback cycle for improving agent performance."""

from semideus.evolution.history import EvolutionHistory
from semideus.evolution.loop import EvolutionLoop, EvolutionResult
from semideus.evolution.mutations import (
    AgentSystemPromptMutation,
    ConfigMutation,
    Mutation,
    MutationType,
    SkillChainMutation,
    SkillCreationMutation,
    SkillPromptMutation,
    SkillToolMutation,
    parse_mutations,
)
from semideus.evolution.sandbox import WorktreeSandbox
from semideus.evolution.strategy import DefaultEvolutionStrategy

__all__ = [
    "AgentSystemPromptMutation",
    "ConfigMutation",
    "DefaultEvolutionStrategy",
    "EvolutionHistory",
    "EvolutionLoop",
    "EvolutionResult",
    "Mutation",
    "MutationType",
    "SkillChainMutation",
    "SkillCreationMutation",
    "SkillPromptMutation",
    "SkillToolMutation",
    "WorktreeSandbox",
    "parse_mutations",
]
