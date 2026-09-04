# LLM-Manager Phase 6 引き継ぎプロンプト

以下を新しいチャットの最初のメッセージとして使用してください。

---

LLM-Managerの作業を引き継ぎ、Phase 6 Hardening と MVP Releaseから続行してください。

## 作業場所と状態

- `/home/yoshimi/WorkSpace/LLM-Manager`
- branch: `main`
- Phase 0〜5完了。Phase 5 closure根拠は`docs/validation/phase5-closure-audit-2026-09-04.md`
- production GUIで完成・公開済みのmutation routeはlocal user Applyと単一OpenCode target restoreだけ
- local root、SSH user、SSH rootは固定理由でI/O前にfail closed

## 最初の作業

Phase 6の最初のMVP blockerであるlocal root production Apply経路を続ける。Ollama root planning、production local helper診断、target別GUI planning、local root Apply task compositionは完了済み。availabilityはまだ未公開。

1. default rule catalog、optimization要件、setting allowlist、Ollama plannerを照合し、root Ollama recommendationをGUIで生成できるかDoD監査する。
2. 根拠のない「最適値」を追加せず、既存の検証済みruleだけで閉じられる最小sliceを決める。materialな推奨仕様変更が必要ならユーザーへ確認する。
3. 実PolicyKit Gateが必要な場合は既存Gate専用targetだけを使い、実Ollama/OpenCode設定や既存systemd unitを変更しない。
4. root recommendation→Review→Applyの全経路Gate完了後だけ`local_root` availabilityを公開する。
5. 全必須検査後、commitして`origin/main`へpushする。

## Phase 6残件分類

- MVP blocker: local root／SSH user／SSH root production Applyと手動restore、正式GUI deb、利用者向けbackup/rollback/recovery文書、security/privacy review
- acceptance/hardening: Ubuntu 26.04/Debian 13最終matrix、performance、長時間Agent、長文layout、実display/accessibility、window close待機UX、完成したGUI経路からのSSH切断再Gate
- Post-MVP: 複数host、自動benchmark、追加client/runtime、telemetry履歴、外部rule配布

## 安全境界

- GUI全体をrootで起動しない。
- 実Ollama/OpenCode設定、既存systemd unit、SSH設定を無断変更しない。
- passwordを尋ねず、argv/stdin/logへ渡さない。
- venv作成、`pip install`、main workstationへのdependency installを行わない。
- inventory/reconciliationをmutation authorityにしない。
- 未完成routeへ既存recovery/retention/deletion helper commandを流用しない。
- restore/delete/cleanupを自動実行しない。

## 必須検査

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m compileall -q src tests setup.py
bash -n packaging/verify-deb.sh
bash -n packaging/remote/build-deb.sh packaging/remote/verify-deb.sh
git diff --check
```

開始時と完了時に、現在・次の作業が何Phaseか明示してください。
