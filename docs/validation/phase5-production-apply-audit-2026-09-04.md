# Phase 5 Production Apply Connection Audit — 2026-09-04

## Decision

Production GUIからのApplyは、4経路すべて現時点では未接続を維持する。Phase 4 coreの各部品が存在することと、GUIが安全にproduction mutationを開始できるcompositionが完成していることは同一ではない。

| Route | Existing core | Missing production GUI boundary | Decision |
|---|---|---|---|
| local user | `SafeApplyCoordinator`、atomic executor、local backup | private production roots、Secret Service、audit/journal、runtime validatorを束縛したcomposition | fail closed |
| local root | privileged coordinator、PolicyKit helper、local backup | helper readiness、PolicyKit staging/invoker、backup、journal、validatorのproduction composition | fail closed |
| SSH user | read-only SSH adapter、user staging primitives、dual-copy policy | user設定のatomic write、remote recovery copy、rollback/result transport | fail closed |
| SSH root | dual-copy root recovery、sudo broker、root journal evidence | remote privileged Apply request/result/journal commandとprotocol | fail closed |

remote sudo invokerの固定allowlistは`invoke-recovery`、`invoke-retention`、`invoke-deletion`だけである。未定義のApplyを既存commandへ見立てて実行しない。

## Implemented Gate

`AssessProductionApplyAvailability`はreport ID/hash、host ID、ChangeSet存在、全changeのprivilege一貫性をI/Oなしで検証し、4 routeを決定論的に分類する。全routeを`available=false`とし、個別のstable reason codeを返す。GUIはproduction factoryがない場合にrouteと不足境界を日本語・英語で表示し、実行buttonを無効化する。

```text
python3 -m unittest tests.test_apply_availability tests.test_ui_i18n tests.test_ui_qt_window tests.test_ui_workflow -v
Ran 23 tests
OK
```

実Ollama/OpenCode、systemd、SSH設定、backup、PolicyKit、sudoへのmutationは行っていない。次はlocal user routeだけを対象にproduction compositionのsandbox Gateを構築する。
