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

restore専用journal/auditとimmutable authorization consumptionを実装し、開始前の保存失敗ではmutationしないこと、commit後の結果保存失敗をunknownとして隠さないことをfault injectionで検証する。GUIの復元実行buttonはまだ設けない。
