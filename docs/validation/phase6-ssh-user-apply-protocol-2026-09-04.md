# Phase 6 SSH user Apply protocol boundary — 2026-09-04

## 結論

SSH user routeのread-only前半は既存のOpenSSH host adapter、host fingerprint照合、OpenCode診断、推奨、実行直前の再取得、source-span差分生成で構成済みである。不足していたmutation境界の最初のsliceとして、unprivileged remote helperの固定`user-apply` protocolとsandbox executorを追加した。

この変更だけではproduction routeを有効化しない。local authoritative + remote recovery copyの双方の検証、rollback、runtime validation、journal/audit、GUI compositionが未接続だからである。

## 閉じた境界

- canonical requestはrequest ID、plan ID、change-set hash、backup ID、local manifest hash、host ID/fingerprint、target、before/after hash、requested/expiry時刻を束縛する。
- targetはremote user home配下の`.config/opencode/opencode.jsonc`、`opencode.json`、`config.json`だけを許可する。
- helperはroot実行、非canonical/期限切れ/tamper request、stale target、symlink、owner不一致、余分またはhash不一致のpayloadを拒否する。
- writeは既存atomic file primitiveを使用し、直後のfile hashを照合してrequest identity付きimmutable resultを保存する。
- shell text、任意argv、任意absolute path、passwordはprotocolへ含めない。
- OpenSSH transportはpayloadを先、canonical requestを最後に転送し、固定`user-apply <request-id> <request-hash>`だけを実行する。resultはbounded read後に全request bindingを照合する。
- SSH切断後の確認は同じcanonical requestから`result.json`をread-only取得し、Applyを再実行しない。

## Sandbox evidence

protocol/executorとOpenSSH transportのfocused 12件で、成功、stale precondition、target/hash tamper、root実行拒否、request-last順序、result binding、取消、read-only reconciliationを確認した。実SSH hostおよび実OpenCode設定へのmutationは行っていない。

## 次のslice

remote targetのread-only snapshotからlocal authoritative encrypted backupを生成する境界を追加した。SSH host ID/fingerprintを再確認し、allowlist済みtargetをstat→bounded read→statで観測してmetadata/hashが変化していない場合だけ、ChangeSetのbefore hashへ一致するcaptured snapshotを永続化する。通常のlocal backupも同じ永続化内部経路を使うが、外部取得snapshotだけはbefore hash一致を必須にする。

次はこのlocal正本を既存のroot-owned remote recovery copyへ接続する。remote stagingだけがSSH user所有であり、恒久copyと独立鍵はADR-0009どおりremote root所有を維持する。双方の検証成功後だけApply transportを呼ぶcoordinatorへ接続する。

## Dual-copy preparation

mutationを行わない`PrepareSshUserApply`を追加した。exact report/plan/approvalとSSH fingerprintを再照合し、単一allowlist済みnon-root fileだけを受け付ける。`SshSnapshotLocalBackupStore`と既存`DualCopyPrivilegedBackupStore`を通したlocal manifestおよびroot-owned remote receiptの全checkが成功した後に限り、検証済みlocal backup本文からpayloadをrenderし、manifest hashを含むcanonical Apply requestを生成する。片側copy失敗時はbackup本文の再読込やApply request生成へ進まない。

sandbox root recovery storeを使う統合caseを含むfocused 4件で、local captured copy、独立remote AES-GCM key scope、両copy verify、remote failure、report/fingerprint/target/stale bindingを確認した。preparation serviceはApply transportを保持せず、rollback protocolが完成するまでmutationを構造的に開始できない。

次は同じmanifest/requestへ束縛したSSH user rollback protocolと、Apply result・runtime validation・rollback終端を管理するcoordinatorを構築する。

## Fixed rollback protocol and transport

unprivileged remote helperへ固定`user-rollback` operationを追加した。canonical rollback requestはApply request hash、plan/change set、backup/local manifest、host ID/fingerprint、target、期待する現在のafter hash、元の存在有無・content hash・mode、短いexpiryを束縛する。現在hashがApply結果から変わっていればmutation前に停止する。元が存在した場合はlocal正本由来payloadをrequest-last staging後に元modeでatomic replaceし、元が不存在なら単一unlink＋directory fsyncを行う。

OpenSSH transportは固定helper argvだけを呼び、bounded canonical resultの全bindingを照合する。切断後は同一requestのresultをread-only取得し、rollbackを自動再実行しない。existing/created target、stale、payload/tamper、root拒否、取消、reconciliationを含むfocused 11件が成功した。次はpreparationが保持するmanifestからrollback requestを生成し、Apply・validation・rollback終端をcoordinatorへ接続する。

## Apply/validate/rollback coordinator

`PrepareSshUserRollback`はPrepared Applyと同一のreport、approval、change set、manifest、host fingerprint、Apply request/payloadを構造的に再照合し、両backup copyを再検証してからlocal正本だけを復元payloadにする。Apply開始後は元approvalの期限切れで安全rollbackを妨げず、新しいrollback request自体へ独立した5分期限を付ける。

`SshUserSafeApplyCoordinator`はapproved audit、dual-copy preparation、manifest/request-bound journal、固定Apply、runtime validation、固定rollback、terminal audit/journalを一つにした。Applyまたはrollback transport切断時は同一immutable resultをread-only取得し、mutationをretryしない。Apply resultを確認できない場合はafter hashを推測してrollbackせず`RECOVERY_REQUIRED`、validation失敗はrollback、rollback resultも確認不能なら`RECOVERY_REQUIRED`とする。Apply後のユーザーcancelでも安全rollbackには新しい非cancel tokenを使用する。

期限切れ後rollback factory、commit、validation rollback、Apply/rollback切断reconciliation、両copy失敗、unknown Apply、rollback不能、cancel-after-Applyを含むfocused 13件が成功した。次はproduction compositionに必要なremote home/config discovery、helper readiness、Secret Service、sudo authorization、state rootsを監査する。
