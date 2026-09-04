# Phase 5 restore route closure audit (2026-09-04)

## 結論

- production手動restoreとして完成しているのは`local_user`の単一OpenCode targetだけである。
- `local_root`、`ssh_user`、`ssh_root`はMVPの最終要件から除外しないが、対応するproduction Apply経路と安全なrestore protocolが未完成な間は接続しない。
- Apply/Validate失敗時の自動rollback（FR-ROLLBACK-01）はPhase 4 coordinatorが担う。Backup/Restore画面の手動restoreは別のmutation authorityであり、既存rollbackやremote recovery helperを暗黙に再利用しない。
- SSH inventoryは既知operationのevidence取得や明示prune内部一覧では代替できない。固定read-only列挙protocol、host fingerprint binding、user/root別のatomic restore、journal reconciliation、実SSH Gateが揃うまでfail closedとする。

## 実装したclosure境界

- `AssessProductionRestoreAvailability`が`local_user`、`local_root`、`ssh_user`、`ssh_root`を決定論的に評価する。
- production entrypointは完成済み`local_user`だけを明示的に有効化する。既定は全経路無効である。
- Backup/Restore画面はSSH host選択時、inventory factoryを呼ぶ前に固定理由を英日表示し、再読込buttonを無効化する。
- local root backupは現在のlocal-user state/inventoryに混在させない。将来はprivileged inventory/restore protocol完成後に別経路として有効化する。

## 検証

- 4経路の既定fail-closed理由と、`local_user`だけを明示的に有効化できることをunit testで確認した。
- production `main()`がApplyとrestoreの双方で`local_user`だけを公開することを確認した。
- main host全test: 452件成功、PySide6依存14件と明示Secret Service Gate 2件の計16件skip、0.518秒。
- Ubuntu 26.04 / PySide6 6.10.2 Gate: `QtRuntimeTests.test_ssh_backup_restore_route_is_disabled_before_inventory_io` 1件成功、0.061秒。SSH host選択時に固定理由が表示され、再読込が無効でinventory I/Oが0回であることを確認した。
- Gate artifact SHA-256: `52e3324e88de8d673b0cb0c90e8e1687990c8fc7f31ae033036e38d693d417be`。
- compileall、local/remote packaging shell構文、`git diff --check`成功。
- 実Ollama/OpenCode設定、systemd、SSH設定は変更しない。

## 次の判断点

Backup/Restore画面のlocal-user vertical sliceはclosure条件を満たした。次はPhase 5全体のDoD監査を行い、残るGUI項目をMVP blocker、明示的な後続、実環境acceptanceに分類する。
