# Phase 5 Approval Invalidation Validation — 2026-09-03

## Scope

Reviewに表示したChangeSetへの明示承認checkboxとstale失効を実装した。Apply、backup、file write、PolicyKit、sudoは呼び出さず、Ollama、OpenCode、systemd、SSH設定を変更していない。

## Contract

- ChangeSet生成が成功し、Reviewがcurrentかつerrorなしの場合だけ承認可能にする。
- 承認状態は表示中の`change_set.content_hash`へ束縛する。
- checkbox解除は承認を即時取り消す。
- plan期限をworker完了時とcheckbox操作時に再検査し、期限到達timerでも`stale_plan`へ失効させる。
- host変更、再診断、profile変更、selection変更では承認とChangeSet bindingを破棄する。
- staleまたは生成失敗時はdiffと承認controlを表示・操作可能にしない。
- locale切替は状態を変えず、承認説明を日本語・英語で再描画する。

## Results

Qt非依存testでhash binding、明示取消、期限切れ拒否、既存承認の失効、profile/selection相当のbinding破棄を確認した。

Ubuntu 26.04 VM、Python 3.14.4、PySide6 6.10.2、`QT_QPA_PLATFORM=offscreen`で、ChangeSet Review後のcheckbox承認と500 ms plan期限到達後の自動解除・`stale_plan`表示を確認した。

```text
python3 -m unittest tests.test_ui_qt_runtime tests.test_ui_workflow tests.test_ui_i18n -v
Ran 20 tests in 0.638s
OK
```

PySide6の追加導入は行っていない。ApprovalRecord生成、backup policy/plaintext確認、Apply/Results接続は後続Phase 5 Gateとする。
