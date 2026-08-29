from llm_manager.domain.models import OptimizationProfile

BALANCED = OptimizationProfile(
    profile_id="balanced",
    version=1,
    name="Balanced",
    goals=("responsiveness", "quality", "resource_balance", "stability"),
    constraints=("avoid_unverified_maxima", "preserve_os_headroom"),
)

CODING = OptimizationProfile(
    profile_id="coding",
    version=1,
    name="Coding",
    goals=("code_quality", "interactive_latency", "editing_context"),
    constraints=("prefer_iteration_speed", "require_model_alignment"),
)

AGENT = OptimizationProfile(
    profile_id="agent",
    version=1,
    name="Agent",
    goals=("long_running_stability", "tool_calls", "context_growth", "recovery"),
    constraints=("bounded_timeouts", "memory_headroom", "compaction_enabled"),
)

PROFILES = (BALANCED, CODING, AGENT)
