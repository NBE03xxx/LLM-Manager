# Phase 5 PySide6 GUI closure audit (2026-09-04)

## Decision

Phase 5は完了とする。6工程の画面、Qt非依存presentation、host単位QThreadPool worker、cancel、stale approval、英日表示、local/SSH read-only診断、local user Applyと単一target restoreのproduction vertical sliceが揃い、Phase 5 ExitであるGUI acceptance経路とUI thread非blockingを満たした。

これはMVP release完了を意味しない。未完成のmutation経路を完成済みとみなさず、production entrypointはlocal userだけを公開し、それ以外をI/O前に固定理由でfail closedにする。

## Workflow audit

| Workflow | Phase 5 evidence | Classification |
|---|---|---|
| Hosts / Diagnose | LocalとOpenSSH alias、strict host identity、外部terminal ControlMaster、partial/error/cancel、Qt worker | Phase 5完了 |
| Recommendations | Balanced/Coding/Agent、説明・影響・risk・actionable/read-only、英日再描画 | Phase 5完了 |
| Review | report/host/config再検証、masked diff、root/restart、backup policy、exact approvalとstale失効 | Phase 5完了 |
| Apply / Results: local user | production composition、COMMITTED/ROLLED_BACK/RECOVERY_REQUIRED、cancelとhost lock | Phase 5完了 |
| Backup / Restore: local user | strict restart inventory、metadata-only preview、exact approval、単一target restore、immutable evidence、明示refresh | Phase 5完了 |
| local root / SSH user / SSH root mutation | 経路別availability、固定理由、button無効、SSH inventory I/Oなし | fail closedでPhase 5 UI境界完了、MVP blocker |

## Requirement and DoD classification

### Phase 5 closure criteria

- AC-05: Reviewに対象、masked diff、root/restart、backup policyを表示する。
- AC-09: QThreadPool上で外部処理を実行し、Qt event-loop sentinel、cancel signal、host lock、終端状態を検証する。進捗は現段階ではworkflow/transaction stage (`running`, `cancel_requested`, `committed`, `rolled_back`, `recovery_required`) として表示する。
- AC-10: UIからprocess/network/privilege/infrastructureへの直接依存を静的検査で拒否する。
- AC-15: ja/en、unsupported localeの英語fallback、主要workflowと安全理由のcatalog完全性を検証する。

### MVP blockers carried into Phase 6

1. local root production Applyと手動restoreを、PolicyKit request、strict inventory、journal/resultまでGUIからend-to-end接続する。
2. SSH user/root production Applyと手動restoreに、固定protocol、dual-copy backup、fingerprint binding、atomic mutation、切断後journal reconciliationを接続する。
3. GUI entry point、desktop file、icon、翻訳catalogを正式debへ含め、Ubuntu 26.04とDebian 13でinstall/upgrade/uninstallをGateする。
4. 利用者向けbackup/rollback/recovery手順、既知制限、security/privacy reviewをrelease evidenceとして閉じる。

### Explicit Phase 6 acceptance/hardening

- 対応OSと基準Ollama/OpenCodeの最終read-only matrix。実製品設定のmutationは別途明示承認がない限り行わない。
- performance基準、長時間Agent scenario、長文layout、実display/accessibility、window close中の安全な待機UX。
- SSH転送切断とroot journal reconciliationの既存core Gateを、完成したproduction GUI経路から再検証する。

### Post-MVP

複数host orchestration、自動benchmark、追加client/runtime、telemetry履歴、外部rule配布は既存scopeどおり対象外とする。

## Safety conclusion

local root/SSH経路を既存recovery/retention/deletion helperへ見立てて接続しない。inventory snapshotをmutation authorityにせず、restore authorizationは一回消費し、`PARTIAL`/`FAILED`/`UNKNOWN`後は新しい明示requestを要求する。したがってPhase 5を閉じても未完成経路の安全境界は拡張されない。

