from __future__ import annotations

from dataclasses import dataclass

from llm_manager.domain.models import DiagnosticReport, OptimizationProfile, Recommendation

from .rules import Rule


@dataclass(frozen=True, slots=True)
class RuleEngine:
    catalog_version: str
    rules: tuple[Rule, ...]

    def evaluate(
        self, report: DiagnosticReport, profile: OptimizationProfile
    ) -> tuple[Recommendation, ...]:
        candidates = [
            recommendation
            for rule in self.rules
            if (recommendation := rule.evaluate(report, profile)) is not None
        ]
        return self._resolve_conflicts(candidates)

    def _resolve_conflicts(
        self, recommendations: list[Recommendation]
    ) -> tuple[Recommendation, ...]:
        by_setting: dict[tuple[str, str], list[Recommendation]] = {}
        for item in recommendations:
            by_setting.setdefault((item.target, item.setting_key), []).append(item)
        resolved: list[Recommendation] = []
        priority = {rule.rule_id: rule.priority for rule in self.rules}
        for key in sorted(by_setting):
            group = by_setting[key]
            values = {repr(item.recommended_value) for item in group}
            if len(values) == 1:
                resolved.append(max(group, key=lambda item: (priority[item.rule_id], item.rule_id)))
                continue
            conflict_ids = tuple(sorted(item.recommendation_id for item in group))
            resolved.extend(
                Recommendation(
                    recommendation_id=item.recommendation_id,
                    rule_id=item.rule_id,
                    rule_version=item.rule_version,
                    target=item.target,
                    setting_key=item.setting_key,
                    current_value=item.current_value,
                    recommended_value=item.recommended_value,
                    reason=item.reason,
                    severity=item.severity,
                    confidence=item.confidence,
                    impact=item.impact,
                    risk=item.risk,
                    requires_restart=item.requires_restart,
                    requires_root=item.requires_root,
                    evidence=item.evidence,
                    actionable=False,
                    conflicts_with=tuple(value for value in conflict_ids if value != item.recommendation_id),
                )
                for item in sorted(group, key=lambda value: value.recommendation_id)
            )
        return tuple(sorted(resolved, key=lambda item: item.recommendation_id))
