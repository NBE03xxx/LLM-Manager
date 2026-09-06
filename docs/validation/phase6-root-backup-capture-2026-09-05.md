# Phase 6 root backup capture/encryption/publication — 2026-09-05

現在・次ともPhase 6。`CaptureRootBackup`、`LocalRootBackupKeys`、`decrypt_root_backup`を追加した。実一時fileとAES-GCMでsandbox検証し、production helper/PolicyKit/GUIには未接続。

## 採取と鍵

採取は、検証済み・workflow binding付きの既存HelperRequest内に固定drop-inのATOMIC_REPLACEが1件ある場合だけを対象にする。backup/host/source request hashはその要求から導出し、ユーザー提供plaintextやmanifestをimportしない。呼出側によるPolicyKit認可確認とFDの安全なanchorは引き続き必要で、request hashだけを認可としない。

固定basenameをtrusted parent FDからO_NOFOLLOW/O_NONBLOCKで読み、regular file・root:root 0644・単一hardlink・最大16 MiB、前後のinode/metadataとdirectory entryを確認する。before hashをApply requestと照合し、暗号化後とrecord公開前にも再観測する。親directoryが未作成の場合のproduction openerや、Applyまで対象を固定するlockは未実装である。

鍵は別のanchored root:root 0700 directoryから`<key_id>.key`（root:root 0600、32 byte、単一hardlink）を読む。`local_root` scopeだけを受け入れ、remote_rootやSecret Serviceの鍵を推測流用しない。鍵の作成・provisioningはこのsliceの対象外であり、欠落・不正時は停止し、平文へfallbackしない。

既存`AesGcmBackupCipher`へ`local_root` scopeを追加してAES-256-GCMを再利用する。AADにはbackup ID/固定targetに加え、local root scope、host ID、source Apply request hash、元file状態を束縛する。暗号化直後に復号して元bytesを照合する。読取後の復号もenvelope hash、AEAD、plaintext hashを確認する。

Base64 JSON envelopeは16 MiB plaintextより大きくなるため、readerの旧17 MiB上限を共通`MAX_ENVELOPE_BYTES`（Base64展開分＋4096 byte）へ合わせた。plaintextの16 MiB上限は変えていない。

## 公開と中断

backup directoryの独立open descriptionに対してnonblocking exclusive flockを取得する。readerはshared flockを使い、同じborrowed FDを共有する呼出しでもlock変換で競合を回避しない。busyは待たずに拒否する。

payloadを0600の一意`.pending`へ書き、file fsync、既存pathを上書きしないlink/unlink、directory fsyncを行う。その後にcanonical recordを同じ方式で公開し、最後にdirectory fsyncを完了する。recordがcommit markerであり、元target不在ならpayloadなしのrecordだけを保存する。平文はbackup directoryへ書き出さない。

2 fileを一つのfilesystem transactionでatomicにする実装ではない。recordを最後に公開し、readerのlock/type/nlink/hash確認により途中の組を受理しない。例外・cancel時のpending/orphanは自動削除せず、同じbackup IDへの再実行は拒否する。最後のdirectory fsync失敗では組が見えていても`root_backup_capture_incomplete`を返し、成功扱いせずreconciliationを要求する。

## 検証

新規14 testを追加。正常採取→暗号化→reader→AEAD復号、元file不変、absence、鍵欠落/scope/mode/size、重複保存、採取中変更、symlink、不正mode、stale hash、payload/marker/final directory fsync失敗、cancel、期限切れ、busy lock、shared borrowed FDの競合、AADのhost/source/元状態bindingを確認した。

全589 test完走（566成功・23 skip）。compileall、local/remote packaging shell syntax、desktop validation、diff check成功。sandboxは明示owner UID/GIDを使い、実root/PolicyKit Gateとは区別する。実VM・Ollama/systemd・既存backup/key・SSHは操作していない。

次もPhase 6。鍵provisioningと固定source/key FD opener、trusted origin/review/attempt storeのadapterを整備してpreflightへ接続する。capture完了とApply開始を結ぶlock、crash reconciliation、retention、特権dispatchとOS/Qt Gateは未完了。root routeは非公開のまま、すべて未コミットで保持する。保存済みdeb/SBOMを今回codeの根拠にはしない。
