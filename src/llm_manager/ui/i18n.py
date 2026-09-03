from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_LOCALES = ("en", "ja")

_ENGLISH = {
    "app.title": "LLM Manager",
    "nav.hosts": "Hosts",
    "nav.diagnose": "Diagnose",
    "nav.recommendations": "Recommendations",
    "nav.review": "Review Changes",
    "nav.results": "Apply / Results",
    "nav.backups": "Backup / Rollback",
    "status.idle": "Ready",
    "status.running": "Running",
    "status.partial": "Completed with warnings",
    "status.success": "Completed",
    "status.failed": "Failed",
    "status.cancel_requested": "Cancellation requested",
    "action.diagnose": "Diagnose",
    "action.cancel": "Cancel",
    "action.approve": "Approve reviewed changes",
    "profile.balanced": "Balanced",
    "profile.coding": "Coding",
    "profile.agent": "Agent",
    "recommendations.summary": "{total} recommendations ({actionable} actionable)",
    "recommendation.change": "{setting}: {current} → {recommended}",
    "recommendation.ollama_unavailable.reason": "OpenCode expects Ollama, but its API is unavailable.",
    "recommendation.ollama_unavailable.impact": "Restore or review the Ollama connection.",
    "recommendation.opencode_unsupported.reason": "Observed OpenCode {observed}; verified baseline is {baseline}.",
    "recommendation.opencode_unsupported.impact": "Keep changes read-only until compatibility is verified.",
    "recommendation.agent_compaction.reason": "Enable {setting} for bounded long-running agent context.",
    "recommendation.agent_compaction.impact": "Reduces unbounded context growth.",
    "severity.low": "Low",
    "severity.medium": "Medium",
    "severity.high": "High",
    "state.actionable": "Actionable",
    "state.read_only": "Review only",
    "action.review_selected": "Review selected recommendations",
    "review.preview_only": "Preview only — executable change set has not been generated.",
    "review.generating": "Generating an executable change set from the current file…",
    "review.failed": "Change-set generation failed: {code}",
    "review.change": "{target}\n{diff}\nRoot required: {root}; restart required: {restart}",
    "review.approval_required": "Approval is required before Apply can be prepared.",
    "review.approved": "Approved for this exact change set.",
    "state.yes": "yes",
    "state.no": "no",
    "review.summary": "{selected} recommendations selected",
    "error.host_required": "Select a host first.",
    "error.workflow_busy": "Another operation is already running.",
    "error.report_required": "Run diagnosis first.",
    "error.plan_required": "Review a change plan first.",
}

_JAPANESE = {
    "app.title": "LLM Manager",
    "nav.hosts": "ホスト",
    "nav.diagnose": "診断",
    "nav.recommendations": "推奨",
    "nav.review": "変更内容の確認",
    "nav.results": "適用・結果",
    "nav.backups": "バックアップ・復元",
    "status.idle": "準備完了",
    "status.running": "実行中",
    "status.partial": "警告付きで完了",
    "status.success": "完了",
    "status.failed": "失敗",
    "status.cancel_requested": "キャンセル要求済み",
    "action.diagnose": "診断する",
    "action.cancel": "キャンセル",
    "action.approve": "確認した変更を承認",
    "profile.balanced": "バランス",
    "profile.coding": "コーディング",
    "profile.agent": "エージェント",
    "recommendations.summary": "推奨 {total}件（変更可能 {actionable}件）",
    "recommendation.change": "{setting}: {current} → {recommended}",
    "recommendation.ollama_unavailable.reason": "OpenCodeはOllamaを使用しますが、APIへ接続できません。",
    "recommendation.ollama_unavailable.impact": "Ollama接続を復旧または確認します。",
    "recommendation.opencode_unsupported.reason": "検出したOpenCodeは{observed}、検証済みbaselineは{baseline}です。",
    "recommendation.opencode_unsupported.impact": "互換性確認まではread-onlyを維持します。",
    "recommendation.agent_compaction.reason": "長時間のAgent contextを制限するため{setting}を有効にします。",
    "recommendation.agent_compaction.impact": "contextの無制限な増加を抑えます。",
    "severity.low": "低",
    "severity.medium": "中",
    "severity.high": "高",
    "state.actionable": "変更可能",
    "state.read_only": "確認のみ",
    "action.review_selected": "選択した推奨を確認",
    "review.preview_only": "プレビューのみ — 実行可能な変更セットはまだ生成されていません。",
    "review.generating": "現在のファイルから実行可能な変更セットを生成中…",
    "review.failed": "変更セットの生成に失敗しました: {code}",
    "review.change": "{target}\n{diff}\nroot権限: {root}、再起動: {restart}",
    "review.approval_required": "Applyの準備には明示承認が必要です。",
    "review.approved": "この変更セットを明示承認しました。",
    "state.yes": "必要",
    "state.no": "不要",
    "review.summary": "推奨を{selected}件選択済み",
    "error.host_required": "先にホストを選択してください。",
    "error.workflow_busy": "別の操作を実行中です。",
    "error.report_required": "先に診断を実行してください。",
    "error.plan_required": "先に変更計画を確認してください。",
}

_CATALOGS = {"en": _ENGLISH, "ja": _JAPANESE}


def select_locale(locale_name: str | None) -> str:
    if not locale_name:
        return "en"
    language = locale_name.strip().lower().replace("-", "_").split("_", 1)[0]
    return language if language in SUPPORTED_LOCALES else "en"


@dataclass(frozen=True, slots=True)
class Catalog:
    locale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "locale", select_locale(self.locale))

    def text(self, key: str, **arguments: object) -> str:
        template = _CATALOGS[self.locale].get(key, _ENGLISH.get(key, key))
        try:
            return template.format(**arguments)
        except (KeyError, ValueError):
            return _ENGLISH.get(key, key)

    @staticmethod
    def keys(locale: str) -> frozenset[str]:
        return frozenset(_CATALOGS[select_locale(locale)])
