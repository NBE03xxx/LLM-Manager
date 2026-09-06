# Phase 6 local root restore coordinator/executor — 2026-09-05

現在・次ともPhase 6。`ExecuteLocalRootRestore`と`SingleRootRestoreTarget`を追加し、実一時fileで復元まで検証した。production helper、PolicyKit、GUI、実systemctlには接続していない。

## 実行境界

coordinatorは独立caller/host/hashを検証してから、固定target parentの独立open descriptionへnonblocking exclusive flockを取得する。lock下でpreflight、保存review、origin/AEAD/復号の確認を行い、永続attemptと開始auditを作る。attempt保存失敗ではmutationへ進まない。開始audit失敗後はfailed resultを記録して停止する。

mutation前にもreview/origin/currentを照合する。専用backendはroot:root 0644の固定basenameだけを扱い、sourceのregular/no-follow/単一link/hash/metadataを再確認する。元file存在時は0600 stagingに平文をメモリから書き、0644化・file fsync・最終対象照合・期限/cancel guard後にreplaceする。current不在なら非上書きlink/unlinkで作成し、元file不在backupは条件付きunlinkする。最後にdirectory fsyncを行う。

staging途中や不確定なpendingは自動削除しない。次の実行は残存stagingを検出して停止する。期限はstagingのfsync後、実置換/削除の直前にも確認する。既存Apply rollback helper commandは流用していない。

## 結果と監査

diskの復元後にtarget state、注入serviceのreload/restart/validation、最終target stateを確認する。serviceのstrict True以外は成功にしない。Falseはdisk復元済みだがservice検証失敗としてfailed、例外やcancel等はunknownとして記録する。service失敗に対する自動rollbackはしない。

mutation呼出前の失敗はfailed、呼出しへ入った後の例外は、実際に変更されたかを推測せずunknownとする。開始/終了auditはrequest hashと固定state/error codeだけを記録し、設定本文や例外本文を保存しない。終了audit失敗も成功扱いにしない。

attempt後の終端保存は元cancel tokenと分離して実行する。result保存失敗では`RootRestorePersistenceError`を返し、attempt-onlyからの自動再試行を許さない。永続resultが成功した場合だけ、そのresultを返す。process強制終了などBaseExceptionではattemptが残り、次の読取で未完了として扱う。

## 検証

新規14 testを追加。実provisioning/capture/AEAD/origin reader/review-attempt-result store/LocalAuditLog/target fileを使うsandboxで、replace/create/remove、attemptとstart auditの順序、audit失敗、開始audit後のtarget変更、mutation例外、target directory fsync失敗、service失敗、service中のtarget変更、復元後cancel、result保存失敗、target lock競合、staging中期限切れを確認した。

全628 test完走（605成功・23 skip）。compileall、packaging shell syntax、desktop validation、diff check成功。serviceは注入fixtureであり、実systemctl/API検証ではない。実rootの認可/owner/PolicyKit Gateではなくsandbox ownerを明示した。対象の作成/置換/削除は一時directory内だけで、実設定/VM/既存backup/key/SSHは変更していない。

## 次のPhaseと限界

次もPhase 6。固定source opener、trusted review producerの認可、実service validation、privileged composition/CLI、PolicyKitとOS/Qt Gateを進める。現在のtarget flockは本coordinator同士を直列化する。既存Applyや外部root editorまで同じlockへ参加させたわけではない。production公開前に製品内の全対象mutatorを同じ排他契約へ揃え、crash/reconciliationを検証する必要がある。

root routeは非公開、既存変更と今回変更は未コミットで保持。保存済みdeb/SBOMは今回codeの検証根拠にはしない。
