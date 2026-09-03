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

短い有効期限を注入した実Qt timer Gateで、preview期限切れ時にcheckboxが解除・無効化され、stable `stale_restore_preview`表示になることを確認する。復元実行buttonはまだ設けない。
