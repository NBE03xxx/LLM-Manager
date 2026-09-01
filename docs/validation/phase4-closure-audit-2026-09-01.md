# Phase 4 Safe Apply Core Closure Audit — 2026-09-01

## 判定

Phase 4のExit条件「sandbox対象で成功・失敗・復元・復元失敗を安全に再現できる」を満たす。Safe Apply Core、限定特権helper、local正本とremote暗号化copy、retention/deletion、切断後restart recovery、journal reconciliation、immutable evidence retentionはsource/test/evidence間で対応している。次はPhase 5 PySide6 GUIである。

## Closure evidence

- unit/fault injection: Backup → Apply → Validate → Rollback、`RECOVERY_REQUIRED`、stale/改ざん/symlink/permission/timeout/cancel、execution保存失敗をsandboxで検証
- Ubuntu 26.04 desktop: local deb lifecycle、Secret Service create/reload/delete、PolicyKit success/dismiss/deny、Gate専用systemd操作とcleanup
- Debian 13 desktop: stock Python 3.13.5 / cryptography 43.0.0 / SecretStorage 3.3.3で全test、両package lifecycle、正式artifact build/verify/APT simulation、Secret Service、PolicyKit success/dismiss/deny、Gate専用systemd操作とcleanup
- disposable SSH target: helper compatibility、external-terminal sudo、root AES-GCM recovery copy、restart receipt recovery、retention/deletion、転送中切断、root journal evidenceとread-only reconciliation

## 意図的な未実施とPhase 5以降

- 実Ollama/OpenCode設定へのApply/rollbackは行っていない。既存設定・unitを無断変更しない安全境界によるもので、Gate専用unitの成功を製品targetへの実Apply evidenceとは扱わない。
- Debian 13の正式release artifactによる最終install/upgrade smoke testはrelease前Gateとする。Phase 4ではGate controlの実lifecycleと正式artifactのbuild/verify/APT simulationによりsupported minimumとpackage境界を確定した。
- GUI entry point、desktop file、icon、ja/en catalog、Qt event-loop統合、release署名・repository配布・SBOM/license reviewはPhase 5またはrelease作業である。

## 安全境界

closureによってmutation authorityを拡張しない。`PARTIAL`/`FAILED` cleanupはimmutableな明示requestを必須とし、inventory/reconciliationはread-only、`executing` receiptは自動再実行せず、remote失敗時もlocal正本を保持する。staging cleanup以外のmutation retryと実製品target Applyには新たな明示承認が必要である。
