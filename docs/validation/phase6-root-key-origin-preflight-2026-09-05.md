# Phase 6 root key provisioning and origin verification — 2026-09-05

現在・次ともPhase 6。`ProvisionLocalRootKey`と`VerifyRootBackupOrigin`を追加し、sandboxで明示key provisioning→固定target採取→AES-GCM→reader→復号/origin検証→read-only preflightを接続した。実環境・production dispatcherには接続していない。

## 鍵初期配置

固定production key directoryは`/var/lib/llm-manager/local-root-restore/keys`。openerはroot-ownedかつ非writableなancestorをdir_fd/O_NOFOLLOWで辿り、最終root:root 0700を要求する。mkdir/権限修復はしない。

明示provisioningはCSPRNGの32 byteから`<id>.key`と、そのSHA-256を含む`<id>.ready`（双方root:root 0600）を作る。独立open descriptionのexclusive lock、O_EXCLのpending file、file fsync、上書きしないlink/unlink、directory fsync、ready最後の順で保存する。戻り値はkey IDだけで、key bytesは返さない。

providerはshared lockのもとでkey/readyをstrict readし、length/hash/owner/group/mode/nlinkとpending不在を確認する。通常のget_keyは作成・更新せず、未完了保存・key/marker欠落・改変で停止する。既存またはpendingを持つIDへのprovisioningは拒否し、回転・削除・自動修復しない。最終fsync等の失敗は不確定としてreconciliationが必要であり、成功へ読み替えない。

旧sliceのsandbox key fixtureもready付きへ更新した。これは開発中の専用形式の更新であり、既存remote_root keyや実環境のkeyを変換していない。

## Origin verifierとpreflight

root review evidenceに`origin_record_hash`と`source_apply_request_hash`を追加し、preflightは両方のdigestを必須にした。要求のhashを作り直しても、trusted reviewとの完全一致検査は省略できない。将来のreview producerはinventory/manifest/previewと、このorigin参照の対応を独立して確立する必要がある。

verifierはreviewから指定されたorigin recordをstrict readerで読み、host、固定target、元file state、source Apply hashを照合する。存在backupはenvelope hash→AEAD→plaintext hashまで検証し、復号後にrecord/payloadを再読込する。preflightへ返すのは検証済みfile stateだけで、plaintextやmutation authorityは返さない。欠落backupではpayload不在を確認する。

review authenticity/expiryはpreflight側の責務であり、verifier単独の成功を認可にしない。root review store、attempt/result store、固定source opener、Applyとの排他、PolicyKit dispatch、restore executorはまだ未完成。

## 検証

新規11 test（provisioning 7、origin/preflight 4）を追加。実一時fileで鍵の不変性、getによる自動作成なし、cancel/不正entropy、不完全書込、marker欠落/改変/symlink、read/write競合、ready公開失敗、origin不一致、鍵喪失、復号中のpayload変更を確認した。

統合testは実provisioning、AES-GCM、capture、reader、target observation、origin verifierを使用する。reviewとunused-attemptだけはin-memory fixtureであり、productionの認可/replay防止完了ではない。全経路で実対象fileを復元・変更していない。

全600 test完走（577成功・23 skip）。compileall、packaging shell syntax、desktop validation、diff check成功。実VM/鍵/backup/SSH/Ollama/systemdは変更していない。全変更は未コミットで保持し、保存済みdeb/SBOMを今回codeの検証根拠にしない。

次もPhase 6: trusted reviewおよびimmutable attempt/resultの保存形式とstrict adapterを整備し、残るin-memory fixtureを置換する。root restore公開にはexecutor、crash/競合、PolicyKit/Qt/OS Gateまで必要である。
