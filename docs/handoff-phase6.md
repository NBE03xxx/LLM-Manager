# LLM-Manager Phase 6 引き継ぎプロンプト

以下を新しいチャットの最初のメッセージとして使用してください。

---

LLM-Managerの作業を引き継ぎ、Phase 6 Hardening と MVP Releaseから続行してください。

## 作業場所と状態

- `/home/yoshimi/WorkSpace/LLM-Manager`
- branch: `main`
- Phase 0〜5完了。Phase 5 closure根拠は`docs/validation/phase5-closure-audit-2026-09-04.md`
- production GUIで完成・公開済みのmutation routeはlocal user Applyと単一OpenCode target restoreだけ
- local root、SSH user、SSH rootは固定理由でI/O前にfail closed。local rootはcomposition/Gate済みだが、根拠あるactionable Ollama rule確定まで公開を保留する

## 最初の作業

Phase 6のSSH user production Apply経路を続ける。ユーザー判断によりlocal rootは安全にfail closedのまま後続へ送り、SSH userを先行する。SSH diagnosis、remote home/global config discovery、recommendation、fresh read、diff生成、unprivileged fixed Apply/rollback protocol、request-last OpenSSH transport、同一resultのread-only reconciliation、stable remote snapshot、dual-copy preparation、Apply/validate/rollback coordinatorは追加済みだが、availabilityはまだ未公開。

1. 追加済みの内部`SshUserApplyTaskFactory`を、reportを保持するGUI workflowの2引数Apply APIへ安全にadapter接続する。
2. production公開前にsandbox GUI Gateと実SSH VM Gateを行う。切断時は同一immutable resultを再照合し、mutationを自動retryしない。
3. 実SSH Gateが必要になった時点でVMへのSSH Server導入をユーザーへ依頼する。それまでは実VMや実OpenCode設定を変更しない。
4. GUI Results Gate完了後だけ`ssh_user` availabilityを公開し、全必須検査後にcommitして`origin/main`へpushする。

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
