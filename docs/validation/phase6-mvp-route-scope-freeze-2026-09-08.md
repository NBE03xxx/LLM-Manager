# Phase 6 MVP production route scope freeze

## 結論

MVP releaseで公開するmutation routeを次の4経路に固定した。

- local user OpenCode Apply / automatic rollback
- SSH user OpenCode Apply / automatic rollback
- local user OpenCode manual restore（単一target）
- local root Ollama manual restore（採取済みroot backup）

local root ApplyはPolicyKit、composition、rollback、origin capture、installed OSの境界は実装済みだが、設定allowlistだけから未検証の推奨値を作らず、根拠あるactionable Ollama ruleがないためscope外とした。SSH root ApplyとSSH user/root manual restoreは専用protocolが完成していないためscope外とした。

## Fail-closed照合

production entrypointのApply allowlistは`LOCAL_USER`/`SSH_USER`、restore allowlistは`LOCAL_USER`/`LOCAL_ROOT`である。既定空集合は全経路を拒否し、非公開経路は次の固定理由を返す。

- local root Apply: `local_root_apply_rule_pending`
- SSH root Apply: `ssh_root_apply_protocol_missing`
- SSH user restore: `ssh_user_restore_protocol_missing`
- SSH root restore: `ssh_root_restore_protocol_missing`

`ProductionApplyAvailabilityTests`、`ProductionRestoreAvailabilityTests`、`QtProductionCompositionTests`がroute分類、明示allowlist、production注入を検査する。SSH restoreはGUIからinventory I/O前に無効となる。

## 文書同期

`docs/requirements.md`に`FR-ROUTE-01`と`AC-16`を追加し、`docs/mvp-scope.md`に固定matrixとscope外の理由を明記した。README、roadmap、traceability、release checklistも同じ境界へ同期した。非公開経路の内部実装は将来の検証用に保持し、production authorityとは扱わない。

## 環境

- 開始時worktree: clean
- Ubuntu 26.04 VM: `shut off`
- Debian 13 VM: `shut off`
- host system SSH config: `nobody:nogroup` / `0777`
- VM、SSH、実設定、service、backup/keyのmutation: なし

## 検証結果

- focused route/i18n test: 12件成功
- host full suite: 790件中752件成功、38件expected skip（hostにPySide6 runtimeなし）
- `compileall`: 成功
- local/remote packaging shell syntax: 成功
- desktop entry validation: 成功
- local/remote CycloneDX JSON parse: 成功
- `git diff --check`: 成功

現在・次ともPhase 6。次はDebian実display/menu、resolved-environment SBOM/Qt license、final lifecycleのうち、外部条件が揃うGateまたは非変更監査を進める。
