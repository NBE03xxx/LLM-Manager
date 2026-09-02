from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from llm_manager.application.optimization import GenerateOptimizationPlan
from llm_manager.domain.models import DiagnosticReport, OptimizationPlan, OptimizationProfile, Recommendation
from llm_manager.optimization import CATALOG_VERSION, PROFILES, RuleEngine, default_catalog

from .i18n import Catalog

_SENSITIVE_SETTING = re.compile(r"(?i)(api[-_]?key|token|password|secret|credential)")


def generate_recommendation_plan(
    report: DiagnosticReport, profile: OptimizationProfile
) -> OptimizationPlan:
    service = GenerateOptimizationPlan(RuleEngine(CATALOG_VERSION, default_catalog()))
    return service.execute(f"plan-{uuid.uuid4().hex}", report, profile)


@dataclass(frozen=True, slots=True)
class RecommendationItemView:
    recommendation_id: str
    title: str
    reason: str
    impact: str
    severity: str
    actionable: bool


@dataclass(frozen=True, slots=True)
class RecommendationPageView:
    profile_id: str
    profile_name: str
    summary: str
    items: tuple[RecommendationItemView, ...]


def present_recommendations(
    plan: OptimizationPlan, catalog: Catalog
) -> RecommendationPageView:
    items = tuple(_present_item(item, catalog) for item in plan.recommendations)
    actionable = sum(item.actionable for item in plan.recommendations)
    return RecommendationPageView(
        profile_id=plan.profile.profile_id,
        profile_name=catalog.text(f"profile.{plan.profile.profile_id}"),
        summary=catalog.text(
            "recommendations.summary", total=len(items), actionable=actionable
        ),
        items=items,
    )


def profile_by_id(profile_id: str) -> OptimizationProfile:
    try:
        return next(profile for profile in PROFILES if profile.profile_id == profile_id)
    except StopIteration as error:
        raise ValueError("unknown_optimization_profile") from error


def _present_item(item: Recommendation, catalog: Catalog) -> RecommendationItemView:
    current = _display_value(item.setting_key, item.current_value)
    recommended = _display_value(item.setting_key, item.recommended_value)
    return RecommendationItemView(
        recommendation_id=item.recommendation_id,
        title=catalog.text(
            "recommendation.change", setting=item.setting_key, current=current, recommended=recommended
        ),
        reason=catalog.text(item.reason.message_key, **dict(item.reason.arguments)),
        impact=catalog.text(item.impact.message_key, **dict(item.impact.arguments)),
        severity=catalog.text(f"severity.{item.severity.value}"),
        actionable=item.actionable,
    )


def _display_value(setting_key: str, value: object) -> str:
    if _SENSITIVE_SETTING.search(setting_key):
        return "<redacted>"
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
