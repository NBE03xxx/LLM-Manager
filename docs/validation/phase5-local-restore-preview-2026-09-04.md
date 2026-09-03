# Phase 5 local restore preview validation (2026-09-04)

## Decision

local backupの復元操作を接続する前に、strict検証済みmanifestだけからmetadata-only previewを生成し、そのexact previewへ短時間の明示承認を束縛する。backup本文の復号、Secret Service、target読込、restore/rollback/delete/cleanupは呼ばない。

## Binding

previewはhost ID、backup ID、manifest hash、生成時刻、有効期限、manual protection、各targetのpath・元の存在有無・SHA-256・modeをcanonical SHA-256へ束縛する。本文content、暗号鍵、key referenceは表示modelへ含めない。

restore approvalはapproval ID、actor、host ID、backup ID、manifest hash、preview hash、承認時刻、有効期限を保持する。明示reviewがない場合、preview hashの改ざん、別backup、またはpreview期限切れでは承認を生成しない。approval期限は5分またはpreview期限の短い方とする。

## Sandbox Gate

`RestorePreviewTests`と`LocalApplyInventoryTests`の6件が成功した。manifest metadata-only preview、content非露出、明示review、exact binding、tamper/expiry拒否、strict inventoryを確認した。

## Next

Qt Backup/Rollback画面へpreview選択・表示・独立したrestore承認checkboxを接続する。host変更、inventory refresh、backup選択変更、preview期限切れで承認を失効させる。復元実行buttonはまだ設けない。
