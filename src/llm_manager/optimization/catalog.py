from .rules import AgentCompactionRule, OllamaUnavailableRule, Rule, UnsupportedOpenCodeVersionRule

CATALOG_VERSION = "1.0.0"


def default_catalog() -> tuple[Rule, ...]:
    return (
        UnsupportedOpenCodeVersionRule(),
        OllamaUnavailableRule(),
        AgentCompactionRule(
            setting_key="compaction.auto",
            desired=True,
            rule_id="agent.compaction.auto",
            priority=800,
        ),
        AgentCompactionRule(
            setting_key="compaction.prune",
            desired=True,
            rule_id="agent.compaction.prune",
            priority=790,
        ),
    )
