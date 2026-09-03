# Phase 5 Apply Preparation Validation — 2026-09-03

## Scope

Review済みChangeSetから期限付きApprovalRecordを生成し、Resultsへ「Apply未開始」の準備状態を渡すGUI vertical sliceを実装した。Apply worker、backup作成、file write、PolicyKit、sudoは呼び出していない。

## Contract

- Review checkboxとApply準備を別の明示操作にする。
- ApprovalRecordをplan ID、report hash、change-set hash、backup-policy hash、GUI実行userへ束縛する。
- record期限は5分またはplan期限の短い方とする。
- 暗号化OFFでは独立した平文backup risk acknowledgementを必須にする。
- 一般配布は暗号化ON、`LLM_MANAGER_DEVELOPMENT_MODE=1`を明示した開発実行だけOFFを初回既定にし、保存済み設定を優先する。
- ResultsはApproval IDと「Apply未開始」だけを表示し、mutationを開始しない。
- plan期限到達時はResultsからReviewへ戻し、record、diff、承認操作を失効させる。

## Results

application testで全hash、actor、平文ack、最短期限、missing/stale入力のfail-closedを確認した。presenter testでは未承認Results遷移を拒否し、承認IDを保持することを確認した。

Ubuntu 26.04 VM、Python 3.14.4、PySide6 6.10.2、`QT_QPA_PLATFORM=offscreen`で、平文risk未確認時の準備禁止、確認後のResults遷移、「Apply未開始」表示、期限後のReview復帰を確認した。

```text
python3 -m unittest tests.test_ui_qt_runtime tests.test_ui_workflow tests.test_approval tests.test_ui_i18n -v
Ran 24 tests in 0.626s
OK
```

PySide6の追加導入と実system変更は行っていない。次はsandbox/fake Apply workerとResults状態表示のGUI統合である。
