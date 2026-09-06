# Local root manual restore protocol — staged implementation

## Status and scope

Latest connection (2026-09-06): [authenticated Apply origin capture and explicit
administrator setup](validation/phase6-root-apply-capture-setup-2026-09-06.md) are
implemented and tested. Capture holds the helper's target lock through the write
and declared service operations. No automatic provisioning or key replacement is
performed. Installed validation of this new path, cross-request transactions,
normal GUI integration and interactive PolicyKit remain outstanding. Historical
slice notes below describe their state at the time, not the current connection.

The subsequent [bounded inventory and explicit GUI workflow handoff](validation/phase6-root-restore-inventory-workflow-2026-09-06.md)
lists only canonical root-owned summaries for the current host and binds selection
to review and final execution sessions. It remains outside the normal production
menu pending Qt and active-desktop PolicyKit Gates. Cross-request atomic locking
is not claimed; each mutation is independently locked and hash-checked, and an
unsafe later rollback must enter recovery-required handling.

Phase 6の専用契約。request codec、固定root-owned inventory、read-only preflight、review/execute/statusの独立PolicyKit dispatch、復号、mutation、audit、明示GUI workflowまで実装し、installed valid OS Gateも完了した。通常GUIにはavailability Gate付きで登録したが、production allowlistでは`LOCAL_ROOT`を公開せず`local_root_restore_release_gate_pending`で拒否する。active desktop interactive PolicyKit Gateと最終公開reviewが完了するまで、この拒否を解除しない。

初期対象はlocal hostの単一`/etc/systemd/system/ollama.service.d/90-llm-manager.conf`。SSH、任意path/unit、複数file、root以外のowner、0644以外のmodeを含めない。既存Apply rollbackの`HelperOperationKind.RESTORE_FILE`とは別protocolであり、retention/deletion/recovery commandも流用しない。

## Request intent

`infrastructure/local_root_restore_protocol.py`は`llm-manager.local-root-manual-restore` version 1のcanonical UTF-8 JSONを扱う。最大16 KiB、有効期間は最大5分。時刻はtimezone必須で、開始時刻を含み、終了時刻を含まない。未知/欠落field、重複JSON key、余分な空白、異常な数値やUnicodeは拒否する。

| Field | Binding |
| --- | --- |
| `request_id` | 後続のimmutable attempt/resultを識別する一意ID |
| `host_id`, `caller_uid` | 独立して観測したlocal hostと非root呼出元UIDに一致すること |
| `backup_id`, `manifest_hash` | 利用者が選択したbackupのexact manifest |
| `inventory_hash` | レビュー対象となった特権側inventory証拠のhash。producerは未実装 |
| `preview_hash`, `approval_id` | 専用previewと明示承認へのbinding。特権側照合は未実装 |
| `target` | 上記固定drop-in以外は拒否 |
| `current` | レビュー時点の現在targetの存在/hash/mode/UID/GID |
| `backup` | 復元先の存在/hash/mode/UID/GID |
| `requested_at`, `expires_at` | 他のreview/approval期限も超えない短命要求。codecは要求自身の期限だけ検査 |
| `request_hash` | 自身のhash欄を空にしたcanonical requestのSHA-256 |

存在するfile stateはSHA-256とroot:root 0644を全て必須とし、不在stateはhash/metadataを全てnullにする。boolを整数として受理しない。currentとbackupが同じならmutation不要として拒否する。

`current=present, backup=present`は置換intent、`absent/present`は作成intent、`present/absent`は削除intentを表す。単にbackupが不在だったことだけで無条件unlinkしてはならない。current hash/metadataの再検証が必須である。

## Trust boundary

requestとその全hashは呼出元が自由に作成できる。codecの成功は形式・整合性・bindingの確認であり、認可、backupの真正性、復号結果の正当性、replay防止の証明ではない。

`decode_request()`へ渡す`expected_caller_uid`と`expected_host_id`は、将来の特権dispatcherが独立して確認した値でなければならない。request自身、任意environment変数、GUIが渡した値をそのまま期待値に使用しない。`encode_request()`は送信側の形式検証なので、認可用途には使わない。

現行local user backup storeやuser生成manifestを、rootへの任意content書込み権限として信頼しない。privileged inventoryのproducerと、backup origin/target/content hash/ownerを結び付けるroot-owned evidenceがまだ存在しない。この証拠保存方式を確定・実装するまでpreflightを成功させるproduction adapterを作らない。旧backupが証拠を持たない場合も、そのmetadataだけからroot authorityを補完しない。

## Required privileged preflight and execution

1. 専用PolicyKit action/dispatchで実呼出元UIDを確定し、固定protocol/versionを確認する。GUI全体をrootで起動しない。
2. root-owned inventory/backup証拠をstrictに読み、host/backup/manifest/inventory/preview/approvalのbindingと期限を再確認する。unknown entry、改ざん、証拠欠落は停止する。
3. 固定targetと全parentをsymlink追跡なしで確認する。存在/hash/owner/modeがrequest.currentと一致し、regular fileであることを確認する。
4. rootが信頼できるbackup内容を取得し、復号・integrity検証後にもmanifest/current target/期限を再確認する。userが差し替え可能なstaging pathを権限根拠にしない。
5. request hashへ束縛したroot-owned immutable attemptと開始auditをmutation前に永続化する。同一ID異hash、既存attempt、orphan resultは新規mutationとして再実行しない。
6. 単一fileだけをatomic replaceまたはhash条件付きunlinkし、directory fsyncを完了する。競合する特権操作と対象観測〜mutationを直列化する。
7. 固定Ollama unitのdaemon-reload/restartとruntime検証を行う。disk復元成功とservice検証成功を区別してresultへ保存する。失敗時に元Applyのrollback commandを再利用したり、自動再試行したりしない。
8. resultをimmutable保存し、read-only再照合だけで確認できるようにする。mutation後の例外/通信断/永続化失敗は成功とも未実行とも推測せずunknown/attentionを維持する。

上記は後続実装の要件である。専用result schema、root証拠store、lock/crash recovery、read-only照合protocolとCLI引数は未実装。これらの設計・fault injection・実PolicyKit/Qt Gateが揃うまでroute availabilityを変更しない。

## Acceptance gates

- codec: replace/create/remove往復、全hash binding、UID/host不一致、期限境界、型、metadata、no-op、unknown/duplicate/noncanonical/oversized/malformed入力。実装済み。
- legacy separation: 既存Apply decoderが本要求を拒否し、production root restoreが非公開であること。実装済み。
- preflight: rehash済み偽要求、証拠欠落/改変、stale target、期限切れのorchestrationをsandbox検証済み。実root証拠・symlink/親差替え・ownerを検査するproduction adapterは未実装。
- execution: attempt/audit保存失敗、復号前後の変更、競合実行、各crash点、結果保存失敗、service失敗、replay/別hash同IDを検証。未実装。
- integration: sandbox→PolicyKit deny/cancel→両OS→Qt result/再読込を順に検証。実設定は明示された専用Gate以外では変更しない。未実装。

## Read-only preflight orchestration (2026-09-05)

`CheckLocalRootRestore`を追加した。入力はcanonical codecで検証した専用request、独立して観測したcaller UID/host、expected hash、CancellationToken。注入clockで全I/O前後の期限を確認する。

1. requestを検証してから、root側review evidenceをrequest IDで取得する。
2. evidenceのapproved request全体と要求を照合し、承認時刻と期限を検査する。evidenceなし/未知型は停止する。
3. immutable attempt/resultが未使用であることを確認し、現在target stateを照合する。
4. backupのorigin・復号/integrity・metadata検証を専用portに要求し、返された状態をrequest.backupと照合する。
5. review evidence、現在target、request未使用を再読込し、変更を拒否する。
6. request hash、確認時刻、最短期限だけを`CheckedRootRestoreIntent`として返す。

全7 read直後にcancel/要求期限/review期限を再検査する。存在/hash/mode/UID/GIDは値だけでなく型も一致させる。`request_is_unused`はstrict Trueだけを成功とし、Noneや数値1も拒否する。port例外から成功を推測せず、後続I/Oへ進まない。

この結果は権限token、payload、request IDの予約ではない。複数操作をロックする実装もないため、成功後の変更や競合を防止したとは扱わない。将来のexecutorがlock下で再検証し、immutable attemptとauditを保存してからmutationする必要がある。

`RootRestorePreflightPort`は信頼境界を明記した契約のみ。root-owned review/backup producer、厳密なfilesystem reader、decryptor、target observer、attempt storeのproduction adapterはまだ存在しない。sandboxのfake portをproductionへ流用しない。特にno-symlink、root owner、暗号化content真正性を今回のorchestration testで実機確認したとは扱わない。

次の保存境界では、特権側が固定targetから採取した元contentとmetadataへ結び付く証拠が必要となる。GUIのmanifestをroot-owned fileへ単にコピーしても真正性は成立しない。新しいproducer/保存形式/retentionと旧backupの非対応扱いを確定してからadapterを実装する。

## Origin evidence reader (2026-09-05)

`RootBackupEvidenceReader`と固定production directory openerを追加した。保存先・形式・制限・root originの要件は[検証記録](validation/phase6-root-backup-evidence-reader-2026-09-05.md)に記載する。実filesystem上のowner/group/mode、no-follow、hardlink、size、inode差替え、ciphertext hashを検査する。readerはpreflightに未接続であり、producer/鍵/復号/atomic publication、review/attempt storeは引き続き未実装。

## Origin capture and publication (2026-09-05)

[採取・暗号化・公開処理](validation/phase6-root-backup-capture-2026-09-05.md)をsandbox実装した。固定targetを直接採取し、local_root scopeのAES-GCM/AADと復号照合後、payload先行/record最後で保存する。readerのenvelope上限とshared lockも更新した。producerはまだprivileged dispatchから呼ばれておらず、key provisioning、固定source/key opener、review/attempt adapter、Applyとの排他区間は未完成。以前のsliceの「producer/復号未実装」は当時の記録として扱い、現状は本節を優先する。

## Key provisioning and origin preflight (2026-09-05)

[明示key provisioningとorigin verifier](validation/phase6-root-key-origin-preflight-2026-09-05.md)を追加した。root reviewにはorigin_record_hash/source_apply_request_hashを必須とし、実AES-GCM/reader/target observationをpreflightへ統合した。review/attemptはfixtureのままで、認可やreplay防止のproduction完了ではない。鍵はkey/ready方式で、通常readで自動生成しない。次はtrusted reviewとimmutable attempt/resultの実storeを構築する。

## Persistent review/attempt/result (2026-09-05)

[専用store](validation/phase6-root-restore-store-2026-09-05.md)を実装し、preflight統合testのreview/attemptを実fileへ置換した。canonical不変record、expiryと履歴の分離、再実行拒否、pending/orphan、fsync失敗を検証済み。trusted reviewを作るproduction認可経路と、対象lock/audit/executorは未実装。store.beginだけをmutation authorityとして使わない。

## Dedicated execution coordinator (2026-09-05)

[専用coordinator/executor](validation/phase6-root-restore-execution-2026-09-05.md)をsandbox実装した。target排他下のpreflight/attempt/start audit/最終照合と期限guard/単一復元/service fixture/terminal audit/resultまで確認。source観測をcaptureと共通関数へ整理した。実service、trusted review producer、固定source opener、privileged dispatch、他mutatorの同一lock参加、OS/Qt Gateは未完了。production availabilityは変更しない。

## Fixed source and service adapter (2026-09-06)

[固定source opener/service validation](validation/phase6-root-restore-service-2026-09-06.md)を追加した。source parentの固定no-follow traversal、復元Environmentとの一致、固定systemctl操作、loopback-only curl/APIを実装し、模擬commandでcoordinatorへ統合。実service readiness、trusted review producer、privileged CLI/認可、全mutatorの同一lock、OS/Qt Gateは未完了。


## Root restore review producer（2026-09-06）

root側review再計算producerを追加。独立caller/host、root-owned origin、現在のtarget、AEADを照合して専用reviewを保存する。元Apply manifest hashをoriginとAEADへ追加。新規14 test、全653 test（630成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-review-2026-09-06.md`。専用PolicyKit action/CLIとGUI consentは未接続であり、既存Apply actionを流用しない。次もPhase 6: 専用認可/dispatch、全製品mutatorの同一target lock、PolicyKit/OS/Qt Gate。実設定・service・VM・SSH未操作、root route非公開、変更は未コミット。


## Root restore review CLI（2026-09-06）

専用root restore review CLIと固定dir_fd composition、独立PolicyKit action review-system-restore、isolated launcher、deb install/manpage/検証scriptを追加。preview/approveのみで復元実行はない。全661 test（638成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-review-cli-2026-09-06.md`。実PolicyKit/installed deb/GUIは未検証。次もPhase 6: GUI consentと呼出し、専用実行認可/CLI、全mutator lock統合、OS/Qt Gate。root mutation route非公開、実設定・service・VM・SSH未操作、全変更未コミット。


## Root restore review client（2026-09-06）

root復元レビュー専用CLIを呼ぶ非特権clientを追加。固定pkexec/専用entry、120秒timeout、32 KiB応答上限、canonical応答、UID/host/対象/期限/hash、保存receiptを検証する。自動retryなし。実CLIと一時root storeの往復を含む新規9 test、全670 test（647成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-review-client-2026-09-06.md`。GUI consent/production composition、実PolicyKit、専用実行認可、全mutator lock、OS/Qt Gateは未完了。root mutation route非公開、実設定・service・VM・SSH未操作、全変更未コミット。次もPhase 6。


## Root restore review consent dialog（2026-09-06）

root復元レビュー専用の同意sessionとQt dialogを追加。現在/backup metadata・期限・hashを表示し、明示同意後に専用clientでレビューのみ保存する。期限/同意解除/失敗/closeで無効化、重複保存と自動retryを抑止。通常メニューは未公開。host全683 test（654成功・29 skip）、Ubuntu 26.04/PySide6 6.10.2のoffscreen関連22 test（21成功・1 expected skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-review-dialog-2026-09-06.md`。実PolicyKit/installed deb・実display・Debian Gate、root専用実行認可/CLI、全mutator lock、provisioningは未完了。次もPhase 6。実設定・service・SSH変更なし、VM検証物cleanup済み、全変更未コミット。


## Shared helper / root restore target lock（2026-09-06）

既存Apply helperと専用root復元を同じtarget directory flockへ接続。helper要求内のbefore-hash確認・書込み・rollback operation・service操作を排他し、競合/中断staging/取得後期限切れを拒否する。実flock・別process・CLI receipt/replayを含む新規10 test、host全693 test（664成功・29 skip）、必須検査成功。詳細: `docs/validation/phase6-root-target-lock-2026-09-06.md`。排他はhelperの1要求単位で、backup採取〜外部validation〜別rollback要求をまたぐtransaction、origin capture接続、旧版/外部mutator協調は未完了。専用root実行認可/CLI・provisioning・PolicyKit/OS Gateも残件。root route非公開、実設定/service/SSH/VM状態変更なし、全変更未コミット。現在・次ともPhase 6。


## Root restore history reconciliation（2026-09-06）

専用review CLIへread-only `status request-id request-sha256`とstore reconciliationを追加。独立caller UID/host/要求hashを同一shared lock下で照合し、期限切れ後も履歴を読む。鍵/backup/current target不要、attempt-onlyはunknown、欠落/破損を未実行扱いせず、自動retryなし。新規8 test、host全701 test（672成功・29 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-status-2026-09-06.md`。専用実行認可/CLI・production audit・非特権status client/GUI・要求間排他・provisioning・PolicyKit/OS Gateは残件。root mutation非公開、実環境変更なし、全変更未コミット。現在・次ともPhase 6。


## Root restore status client（2026-09-06）

root復元の非特権status clientを追加。exact intentのUID/host/hashと応答schema・時刻・attempt/result digest・state/attentionを検証し、期限切れ履歴を単発照会する。新規7 test（実CLI＋一時store統合含む）、host全708 test（679成功・29 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-status-client-2026-09-06.md`。GUI接続、専用実行認可/CLI・production audit・要求間排他・provisioning・PolicyKit/OS Gateは残件。root mutation非公開、実環境変更なし、全変更未コミット。現在・次ともPhase 6。


## Root review dialog history lookup（2026-09-06）

非公開root review dialogへ明示・単発の履歴照会ボタンを追加。保存成功/結果不明後にexact requestでstatus clientを非同期呼出しし、重複操作・再送・遅延成功を抑止。英日で履歴/unknown/照会失敗を区別する。新規session 3 test成功、Qt 2 testはhost PySide6不在で未実行。host全713 test（682成功・31 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-status-gui-2026-09-06.md`。次は対応VMでQt Gate。専用実行認可/CLI・production audit・要求間排他・provisioning・PolicyKit/OS Gateも残件。通常menu/root mutation非公開、実環境変更なし、全変更未コミット。現在・次ともPhase 6。


## Strict root restore audit（2026-09-06）

root復元専用audit adapterと固定openerを追加。root metadata/no-follow、hash chain/HEAD、request開始終了対応、排他、event先行/fsync/HEAD更新、中断証拠のfail closedを実装。新規9 test（実一時復元coordinator接続含む）、host全722 test（691成功・31 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-audit-2026-09-06.md`。専用実行認可/CLIのproduction composition、要求間排他、provisioning、実PolicyKit/installed deb/OS Gateは残件。root mutation非公開、実環境変更なし、全変更未コミット。現在・次ともPhase 6。


## Fixed root restore composition（2026-09-06）

root復元の固定production compositionとStoredRootRestorePreflightを追加。backup/key/source/store/audit/serviceを接続し、root guard・audit chain事前検査・全FDの例外時解放を実装。新規6 test（実store/復号/target/auditを使うport統合含む）、host全728 test（697成功・31 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-composition-2026-09-06.md`。compositionは認可ではなく、専用実行CLIは未公開。要求間排他・provisioning・PolicyKit/installed deb/OS Gateも残件。実環境変更なし、全変更未コミット。現在・次ともPhase 6。

## Dedicated execution CLI（2026-09-06）

専用execute CLIと独立PolicyKit actionを追加した。短命canonical requestを独立caller
identityと照合して固定compositionへ渡し、保存済みresultだけをbinding検査後に返す。
永続化不明は`execution_unconfirmed`であり自動retryしない。詳細は
[検証記録](validation/phase6-root-restore-execute-cli-2026-09-06.md)。通常GUIからは
未接続で、実PolicyKit/installed deb/provisioning/OS Gate完了まではroute非公開を維持する。

## Unprivileged execution client（2026-09-06）

固定execute entryを一度だけ呼ぶ非特権clientを追加した。正常terminal result以外の
起動後結果はunconfirmedとして自動retryせず、read-only status照合を要求する。詳細は
[検証記録](validation/phase6-root-restore-execute-client-2026-09-06.md)。最終同意GUIへは
未接続で、routeは非公開のまま。

## Final root restore consent（2026-09-06）

保存済みreview receiptと一致する有効期限内のexact requestだけを最終同意sessionへ渡す。
request SHA-256へ束縛した明示チェック後に一度だけexecute clientを起動し、結果不明時だけ
read-only statusを一度照会できる。Qt dialogは対象・現在値・復元値・期限・hashを表示し、
実行ボタンを初期無効、全ボタンを非defaultにする。close中の遅延結果も採用しない。詳細は
[検証記録](validation/phase6-root-restore-final-consent-2026-09-06.md)。host全758 test
（722成功・35 expected skip）と必須検査成功。Ubuntu 26.04/Python 3.14.4/
PySide6 6.10.2でruntime 4件も成功（5件中inverse boundary 1 expected skip）。
fresh dev deb build/verifyも成功（SHA-256
`8b97f31d125a7b6a89dcc68fc4207732f6fffdf9e9ba6f51350275d11a26ef64`）。
通常GUI routeは非公開で、active認証とvalid requestのOS mutation/service Gateは未完了。

## Installed deny and temporary provisioning Gate（2026-09-06）

Ubuntu 26.04の一時snapshot内へ同一fresh dev debを導入し、root-owned launcher/policy/
manpage、installed isolation import、review/executeの独立PolicyKit actionを確認した。
inactive SSHでは両actionがexit 127・stdout 0 byteで拒否され、不正requestもproduction I/O前に
固定error JSONで拒否された。installed provisioningは`/tmp`限定でroot 0600 key/readyの
作成・再読込・重複拒否・自動削除に成功。詳細は
[検証記録](validation/phase6-root-restore-installed-deny-provisioning-2026-09-06.md)。
snapshot revert後に旧package、target/state/artifact不在を確認しVMを`shut off`へ復帰した。
active desktopのinteractive PolicyKit認証は未完了でroute非公開。

## Valid installed OS mutation/service Gate（2026-09-06）

Ubuntu 26.04一時snapshotでinstalled producerから暗号化origin、trusted review、5分期限の
canonical requestを作成し、専用execute entryを一度だけ実行した。固定targetはoriginal hashへ
戻り、実systemd reload/restart、loopback version/tags、0600 attempt/result、strict audit 2件、
read-only committed statusを確認。同じrequestのreplayは拒否されtarget/result不変。詳細は
[検証記録](validation/phase6-root-restore-valid-os-gate-2026-09-06.md)。snapshot revert後に
旧packageと全fixture不在を確認しVMを`shut off`へ復帰。QEMU guest agentからentryを直接実行した
ためactive desktop PolicyKit認証は未完了で、通常GUI routeは非公開を維持する。
