# Phase 5 Sandbox Apply Results Validation — 2026-09-04

## Scope

注入可能なsandbox/fake Apply taskをQt workerで実行し、Resultsへ状態を表示するGUI境界を実装した。production GUIにはApply task factoryを渡さず、実backup、file write、PolicyKit、sudo、Ollama/OpenCode/systemd/SSH設定変更は行っていない。

## Contract

- task入力はReview済み`OptimizationPlan`と期限付き`ApprovalRecord`に限定する。
- Apply開始前にpresenterのprepared approvalを必須とする。
- 診断・ChangeSet生成と同じhost単位lock、QThreadPool、CancellationTokenを使う。
- UIはinfrastructureをimportせず、構造化されたstatus/errorだけを受け取る。
- Resultsにrunning、committed、rollback/recovery/errorを表示し、cancelをworkerへ伝播する。
- productionでfactoryがない場合は実行buttonを無効化し、Apply未接続を表示する。

## Results

Qt非依存testでprepared approvalなしの開始拒否、busy状態、committed outcome保持を確認した。

Ubuntu 26.04 VM、Python 3.14.4、PySide6 6.10.2、`QT_QPA_PLATFORM=offscreen`で、明示Review、平文risk確認、ApprovalRecord準備、fake Apply worker、`committed` Results、plan期限後のReview復帰までを確認した。

```text
python3 -m unittest tests.test_ui_qt_runtime tests.test_ui_workflow tests.test_ui_qt_window tests.test_ui_i18n -v
Ran 25 tests in 0.648s
OK (skipped=1)
```

skipはPySide6が存在する環境でのみ不要になるmissing-PySide negative testである。PySide6追加導入は行っていない。次はlocal user設定、local root、SSH user/rootそれぞれのproduction Apply接続可否を安全境界別に監査する。
