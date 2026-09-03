# Phase 5 local restore preview validation (2026-09-04)

## Decision

local backupの復元操作を接続する前に、strict検証済みmanifestだけからmetadata-only previewを生成し、そのexact previewへ短時間の明示承認を束縛する。backup本文の復号、Secret Service、target読込、restore/rollback/delete/cleanupは呼ばない。

## Binding

previewはhost ID、backup ID、manifest hash、生成時刻、有効期限、manual protection、各targetのpath・元の存在有無・SHA-256・modeをcanonical SHA-256へ束縛する。本文content、暗号鍵、key referenceは表示modelへ含めない。

restore approvalはapproval ID、actor、host ID、backup ID、manifest hash、preview hash、承認時刻、有効期限を保持する。明示reviewがない場合、preview hashの改ざん、別backup、またはpreview期限切れでは承認を生成しない。approval期限は5分またはpreview期限の短い方とする。

## Sandbox Gate

`RestorePreviewTests`と`LocalApplyInventoryTests`の6件が成功した。manifest metadata-only preview、content非露出、明示review、exact binding、tamper/expiry拒否、strict inventoryを確認した。

## Next

## Qt read-only slice

Backup/Rollback画面のinventory選択をworker経由のpreview生成へ接続した。対象path、元の存在有無、SHA-256、modeだけを英日表示し、独立したrestore承認checkboxはexact previewに対する承認だけを生成する。host変更、inventory refresh、backup選択変更でpreviewと承認を破棄する。言語変更の再描画ではpreview loaderを再実行しない。復元実行controlは設けていない。

Ubuntu 26.04/PySide6 6.10.2 offscreen環境で、Qt runtime、accessible boundary、import boundary、英日catalogを含む9件が0.043秒で成功した。PySide6が存在するためmissing-PySide negative test 1件だけをskipした。preview表示、本文非表示、exact承認、inventory refresh直後の承認解除・無効化を確認した。

## Next

## Expiry timer Gate

150 msの有効期限を持つcanonical previewを注入し、承認後にQt timerだけでpreviewとapprovalが破棄されるruntime testを追加した。Ubuntu 26.04/PySide6 6.10.2 offscreen環境で1件が0.192秒で成功し、checkboxの自動解除・無効化とstable `stale_restore_preview`表示を確認した。restoreその他のmutation callは存在しない。

## Next

## Restore preflight

`PrepareLocalRestore`は承認済みpreviewをそのまま実行権限にせず、実行直前にhost単位のstrict manifest一覧を再読込する。canonical preview hash、approval期限、host/backup/manifest hash、protection、全targetのpath・存在有無・SHA-256・modeを再照合する。strict storeが各targetをallowlistへ再検証した後、approval ID、actor、全hash、target一覧、有効期限をcanonical hashへ束縛した短命authorizationだけを返す。

本文content、復号鍵、manifest objectはauthorizationへ含めない。cancel、approval mismatch、preview/manifest変更、unknown/tampered entryではauthorizationを生成せず、restore APIを呼ばない。`RestorePreflightTests`、`RestorePreviewTests`、`LocalApplyInventoryTests`のsandbox 9件が0.007秒で成功した。

## Next

## Sandbox single-target executor

一般的なfilesystemでは複数fileの置換を一つのatomic transactionにできず、既存restoreは途中成功を許す。このため最初のexecutorを単一local user targetだけに制限した。preflightは現在targetの存在有無とSHA-256もauthorizationへ束縛する。executorはauthorizationのcanonical hash/expiry、strict manifest、target一覧、現在状態を復号前に再検証し、backup item読込後にも現在状態を再照合する。既存fileは同一directoryの一時fileから`os.replace`、元が不存在なら単一unlink後にdirectory fsyncする。

authorization/target変更、複数target、cancelはmutation前に拒否する。sandbox 6件が0.005秒で成功し、成功restoreと変更検出時の内容保持を確認した。production composition、GUI button、journal/audit、authorization消費のimmutable replay防止は未接続であり、このexecutorをproductionへ公開しない。

## Next

## Immutable execution evidence and audit

authorization hashごとのimmutable attemptをmutation前に0700/0600 storeへ保存し、同じauthorizationの再実行を拒否する。attemptはhost/backup/manifest/preview/approval/actor/target/時刻を自己hashへ束縛する。開始auditが失敗した場合もattemptを消さず、mutationせず、暗黙retryを許さない。

成功または失敗resultはattempt hash、authorization、manifest、target、state、時刻、errorを別のimmutable自己hash evidenceへ保存する。restart loadはcanonical bytes、filename identity、hash、owner/mode、symlink、1 MiB上限を再検証する。commit後のaudit失敗は`UNKNOWN` evidenceを保存して専用persistence errorへ公開する。commit後のresult保存失敗も、生成済み`COMMITTED` evidenceとcause codeを専用errorから取得でき、未変更とは推測しない。

正常、replay、attempt保存失敗、result保存失敗、開始/完了audit失敗、restart、tamper、metadata不正を含むfocused 12件が成功した。production/GUI compositionは未接続である。

## Next

## Restart execution inventory

restore execution storeの全entry strict一覧を追加した。未知entry、symlink、owner/mode不一致、非canonical record、filename/hash/attempt-result binding不一致、attemptを欠くorphan resultが1件でもあれば部分一覧を返さない。resultのないattemptは`attempt_only`として保持し、attentionを必須にする。自動retry actionは生成しない。

local production inventoryはmanifest/journalに加えてrestore executionをread-onlyで結合し、restore stateとrestore attentionを英日表示する。restore evidenceだけが残るbackup IDも黙って消さない。Ubuntu 26.04/PySide6 6.10.2でQt表示、fault injection、restart/tamper、attempt-only結合を含む12件が0.091秒で成功した。

## Next

local production restore compositionを監査し、Secret Service prompt、authorization有効期限、execution store/audit配置、単一target制限を実環境で安全に満たせるか判定する。明示的な実行controlと実config mutationはまだ接続しない。
