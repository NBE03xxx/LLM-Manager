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
