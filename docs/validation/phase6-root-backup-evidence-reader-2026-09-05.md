# Phase 6 root backup evidence reader — 2026-09-05

現在・次ともPhase 6。root restore用のorigin evidence形式と固定保存先を定義し、実filesystemを読む`RootBackupEvidenceReader`を追加した。producer、鍵生成、暗号化/復号、特権dispatch、restore mutationは未接続。

## 保存契約

保存先は`/var/lib/llm-manager/local-root-restore/backups`（root:root 0700）。各backupは`<backup_id>.json`と、元fileが存在した場合だけ`<backup_id>.bin`（root:root 0600、regular、単一hardlink）から成る。recordはcanonical JSONで、固定drop-in target、host/backup ID、採取元Apply request hash、元fileの存在/hash/root:root 0644、ciphertext hash、key ID、timezone付き採取時刻、record hashを束縛する。recordは16 KiB、opaque ciphertextは17 MiB以内に限定する。

採取元Apply request hashやrecord hashそのものは真正性の証明ではない。将来のroot producerが固定targetを直接採取し、content/metadataを検証して暗号化し、この記録を作る必要がある。user manifestをコピーするimport APIは設けない。root-origin証拠を持たない旧backupは、このreaderが受理する形式へ自動変換しない。

鍵の実保存・AEAD/AAD契約・復号とproducer側のatomic publicationは後続作業。今回の`.bin`はopaque bytesとしてhash照合するだけで、暗号化の妥当性や復号後のplaintext hashは検証していない。欠落・不整合を理由に平文へfallbackしない。

## 読み取り境界

production openerは固定絶対pathを`/`からdir_fdとO_NOFOLLOWで辿り、全ancestorがroot-ownedかつgroup/other writableでないことを確認する。最終directoryはroot:root 0700を要求する。mkdirや修復は行わない。

readerは借用directory FDへ相対openし、requestが提供するpathを使用しない。record/payloadのowner/group/mode/type/nlink/sizeを検査し、O_NONBLOCKでFIFO待機を避け、受信中のsize上限とcancelも確認する。読み取り前後およびdirectory entryのdevice/inode/mode/owner/group/nlink/size/mtime/ctimeを照合して差替えを拒否する。payload照合後にrecordを再読込する。元file不在のrecordではpayload entryがsymlink等でも存在すれば拒否する。

readerのowner_uid/owner_gid引数はsandbox用の明示seam。production openerと将来のprivileged compositionでは既定0を使い、request/GUIから指定しない。borrowed FDの安全なanchorを確認するのは呼出側の責任であり、productionは固定openerを使う。

## 検証

新規12 testで実一時fileを使い、正常readと不変性、不在backup、ciphertext/record改変、symlink/hardlink/FIFO/directory、owner/group/mode、record/payload size、読み取り中のinode差替え、cancel、canonical/型/binding、writable ancestorを検証した。sandboxのowner/groupには実行userのIDを明示している。root実機GateやAEAD復号Gateとは扱わない。

全575 test完走（552成功・23 skip）。compileall、packaging shell syntax、desktop validation、diff check成功。実VM/設定/backup/key/SSHは操作していない。既存変更と今回変更は未コミットで保持し、保存済みdeb/SBOMは本readerを含むartifactの証拠に読み替えない。

次もPhase 6: root採取・暗号化・atomic publicationのproducerと鍵境界、origin照合/復号adapterを実装し、read-only preflightへ接続する。review/attempt store、lock、executor、PolicyKit/Qt/OS Gateも未完成のため、root restore availabilityは変更していない。
