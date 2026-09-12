# Phase 6 SSH切断照合のQt回帰検証 — 2026-09-10

## 結果と範囲

`tests/test_ui_qt_runtime.py` に、実際のQt worker、
`SshUserSafeApplyCoordinator`、一時ディレクトリのjournalを接続する回帰テストを追加した。
transport、backup、runtime validationは既存のテストfixtureを使用する。
実SSH回線の切断、remote helper、Secret Service、OpenCode実行の検証ではない。

全ケースでApply呼出しが切断例外となった後、result読取りで照合する。

| result照合条件 | GUIおよびjournal | mutation呼出し |
| --- | --- | --- |
| Apply結果取得、validation成功 | COMMITTED | Apply 1回 |
| Apply結果取得、validation失敗、rollback切断後に結果取得 | ROLLED_BACK | Apply/rollback各1回 |
| Apply結果取得不能 | RECOVERY_REQUIRED | Apply 1回、rollbackなし |
| Apply結果取得、validation失敗、rollback結果取得不能 | RECOVERY_REQUIRED | Apply/rollback各1回 |

report/plan/approvalがGUIからそのまま渡ることも検査する。

## 実行

- ホスト: `tests.test_ssh_user_apply_coordinator` の6件成功。
- Ubuntu 26.04 VM: 通常system SSHでsource/testsを一時ディレクトリへ転送。
  stock `/usr/bin/python3` とQt offscreenで、新規テスト、既存SSH GUI routeテスト、
  coordinator 6件の計8件成功（新規テストは上記4 subcaseを含む）。skipなし。
- `git diff --check` 成功。
- VMの一時ディレクトリは実行後に削除。package、実設定、SSH trust、VM状態は変更していない。
- 使用量の制約に合わせ全suiteは再実行していない。今回の変更はテストと文書のみ。

## 実機Gateの前提と残件

read-only preflightでUbuntu UID 1000への通常SSH接続成功。
remote helperは未導入。OpenCodeは `/usr/bin/opencode`、`/usr/local/bin/opencode`、
`/home/yoshimi/.opencode/bin/opencode` に存在せず、固定3設定targetも不在。
これは候補pathの観測であり、全filesystemの探索結果ではない。

実GUI SSH Gateは未完了のまま。次回は一時snapshot等の復帰方法を確認し、
remote helper導入、Secret Serviceとremote root backupの認証、
runtime validatorの条件を揃えてから実施する。
fixture validatorを使用する場合は、OpenCode実行を検証済みと扱わない。
最終artifactのSSH切断後immutable result照合とrelease setの残Gateも維持する。
