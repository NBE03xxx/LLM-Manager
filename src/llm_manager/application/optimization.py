from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta

from llm_manager.domain.models import DiagnosticReport, OptimizationPlan, OptimizationProfile, utc_now
from llm_manager.domain.serialization import to_primitive
from llm_manager.optimization.engine import RuleEngine


@dataclass(frozen=True, slots=True)
class GenerateOptimizationPlan:
    engine: RuleEngine
    lifetime: timedelta = timedelta(minutes=30)

    def execute(
        self, plan_id: str, report: DiagnosticReport, profile: OptimizationProfile
    ) -> OptimizationPlan:
        created_at = utc_now()
        recommendations = self.engine.evaluate(report, profile)
        return OptimizationPlan(
            plan_id=plan_id,
            report_id=report.report_id,
            report_hash=stable_hash(report),
            profile=profile,
            rule_catalog_version=self.engine.catalog_version,
            recommendations=recommendations,
            selected_ids=(),
            change_set=None,
            created_at=created_at,
            expires_at=created_at + self.lifetime,
        )


def stable_hash(value: object) -> str:
    encoded = json.dumps(
        to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
