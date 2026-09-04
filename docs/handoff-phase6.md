# LLM-Manager Phase 6 引き継ぎプロンプト

以下を新しいチャットの最初のメッセージとして使用してください。

---

LLM-Managerの作業を引き継ぎ、Phase 6 Hardening と MVP Releaseから続行してください。

## 作業場所と状態

- `/home/yoshimi/WorkSpace/LLM-Manager`
- branch: `main`
- last implementation commit before this handoff: `06628f6 Enable validated SSH user apply route`
- Phase 0〜5完了。Phase 5 closure根拠は`docs/validation/phase5-closure-audit-2026-09-04.md`
- production GUIで完成・公開済みのmutation routeはlocal user Apply、SSH user Apply、単一local OpenCode target restore
- local rootとSSH root Apply、SSH user/root restoreは固定理由でI/O前にfail closed。local rootはcomposition/Gate済みだが、根拠あるactionable Ollama rule確定まで公開を保留する

## 最初の作業

Phase 6 Hardening / MVP Release監査を続ける。ユーザー判断によりlocal rootは安全にfail closedのまま後続へ送り、SSH user Applyを先行して完成・公開した。実装とGateの詳細は`docs/validation/phase6-ssh-user-real-gate-2026-09-05.md`を読む。

1. PySide6 sandbox GUI Gate、実SSH Apply→validation failure→自動rollback Gate、Apply/rollbackの実transport disconnect reconciliation Gate、全Gate evidenceのexact cleanup、SSH user GUI Results Gateが成功済み。
2. VMにOpenCode本体はないため追加済みGate専用runtime validator seamを使用し、production既定`ProductRuntimeValidator`は変更しない。切断時は同一immutable resultを再照合し、mutationを自動retryしない。
3. 実SSH Gateのlocal/remote backup、root key、user staging、helper package/deb、target、Gate用空directoryはcleanup済み。VMのSSH Server、VM user `authorized_keys`、host `known_hosts` entryだけは意図的に保持している。新チャットでは最初に、今後のGate用として維持するか削除するかをユーザーへ確認する。
4. `ssh_user` availabilityは公開済み。直近の全検査は512件成功、ホストにPySide6がないため18件skip。新規SSH Results Qt testはUbuntu 26.04 VMのPySide6 6.10.2で別途成功した。
5. SSH環境の扱いを確定後、`docs/roadmap.md`、`docs/requirements.md`、`docs/traceability.md`を再監査し、残るMVP blockerから次の独立sliceを選ぶ。local rootはactionable Ollama rule不足を解消できるまで公開しない。SSH root ApplyやSSH restoreを既存SSH user protocolの単純な拡張として推測実装しない。

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
