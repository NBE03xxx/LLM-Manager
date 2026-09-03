# Phase 5 Production Apply Connection Audit — 2026-09-04

## Decision

初回監査では4経路すべてを未接続とした。その後local user compositionのsandboxおよびUbuntu desktop実Secret Service Gateが完了したため、production GUIはlocal userだけを選択的に接続する。残る3経路は未接続を維持する。

| Route | Existing core | Missing production GUI boundary | Decision |
|---|---|---|---|
| local user | `SafeApplyCoordinator`、atomic executor、local backup | private roots、Secret Service、audit/journal、runtime validatorを束縛しGate完了 | enabled |
| local root | privileged coordinator、PolicyKit helper、local backup | helper readiness、PolicyKit staging/invoker、backup、journal、validatorのproduction composition | fail closed |
| SSH user | read-only SSH adapter、user staging primitives、dual-copy policy | user設定のatomic write、remote recovery copy、rollback/result transport | fail closed |
| SSH root | dual-copy root recovery、sudo broker、root journal evidence | remote privileged Apply request/result/journal commandとprotocol | fail closed |

remote sudo invokerの固定allowlistは`invoke-recovery`、`invoke-retention`、`invoke-deletion`だけである。未定義のApplyを既存commandへ見立てて実行しない。

## Implemented Gate

`AssessProductionApplyAvailability`はreport ID/hash、host ID、ChangeSet存在、全changeのprivilege一貫性をI/Oなしで検証し、4 routeを決定論的に分類する。呼出側が明示した完成済みrouteだけを`available=true`にでき、既定は空集合でfail closedである。production entrypointは`local_user`だけを明示し、同時に`LocalUserApplyTaskFactory`を注入する。GUIはfactoryの存在だけではなくroute availabilityも要求し、未完成routeでは理由を日本語・英語で表示して実行buttonを無効化する。

```text
python3 -m unittest tests.test_apply_availability tests.test_ui_i18n tests.test_ui_qt_window tests.test_ui_workflow -v
Ran 23 tests
OK
```

Ubuntu 26.04/PySide6 6.10.2 offscreen環境で、production availability、entrypoint composition、i18n、Qt runtimeの14件が成功した。実Qt上でlocal root routeのbuttonが無効かつ理由表示され、同じ画面状態をnon-root local ChangeSetへ切り替えた場合だけ有効になることを確認した。

この接続Gateでは実Ollama/OpenCode、systemd、SSH設定、backup、PolicyKit、sudoへのmutationは行っていない。次は一時config/state rootと実Secret Serviceを使い、GUIからlocal user compositionへ到達するvertical sliceを検証する。

## Local user GUI vertical slice

Ubuntu 26.04/PySide6 6.10.2 offscreen環境で、承認済み`ApprovalRecord`をResultsへ渡し、実`LocalUserApplyTaskFactory`をQt workerから実行するvertical sliceを追加した。`/tmp`内の一時OpenCode config/state rootだけを使い、AES-GCM backup、atomic Apply、validation、hash-chain audit、operation journalを経てGUIへ`committed`が表示されることを確認した。Gate専用memory key providerを使い、Secret Serviceと実製品設定は変更していない。対象1件は0.114秒で成功した。

## Local user failure outcomes

同じUbuntu desktop/PySide6環境で、実`LocalUserApplyTaskFactory`へGate専用runtime validatorとbackup storeを注入し、一時configだけを対象に失敗経路を検証した。runtime validation失敗では暗号化backupから元内容へ復元され、GUIに`rolled_back`が表示された。別caseではrestore failureを注入し、変更後内容が残ると同時にGUIへ`recovery_required`が表示された。2 caseを含む対象1件は0.087秒で成功した。production既定compositionは実`ProductRuntimeValidator`と`LocalBackupStore`を使い、注入点は構成境界の故障検証にだけ利用した。
