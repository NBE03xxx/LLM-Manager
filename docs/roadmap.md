# ロードマップ

Phase 4はclosure auditを完了した。backup evidence retention、明示cleanup、Ubuntu 26.04/Debian 13 desktop・package・PolicyKit Gateを含むSafe Apply CoreのExit条件を満たす。実Ollama/OpenCode設定へのApply/rollbackは安全境界により意図的に未実施であり、Gate専用unitの成功を製品targetへの実Apply evidenceとは扱わない。次はPhase 5のPySide6 GUIである。詳細は[Phase 4 closure audit](validation/phase4-closure-audit-2026-09-01.md)を参照する。

## Phase 0: 設計確定（完了）

- 本文書群の review と受け入れ条件の合意
- Ubuntu 26.04 / Debian 13 / Python 3.14.4 / Ollama 0.33.2 / OpenCode 1.18.25を起点とするversion matrixの作成
- 設定 schema、systemd 配置、OpenSSH/sudo の実環境調査
- PolicyKit、SSH外部端末対話sudo、local+remote backup、任意暗号化、30日・10世代保持のthreat modelとADR作成
- 自動変更 setting allowlist の確定
- 要件IDとtest matrixの対応表確定
- 日本語・英語catalog方針、英語fallback、翻訳完全性checkの確定

成果物: version matrix、setting allowlist、Rule fixture仕様、Privilege/Backup ADR、traceability matrix。

Exit: 主要設計判断がADR化され、残存する実装時Gateが成果物とMVP scopeに明記される。対応要件: FR-HOST、FR-DIAG、FR-OLLAMA、FR-OPENCODE、FR-REC、FR-BACKUP。

設計成果物は[Phase 0 技術調査](phase-0.md)に集約した。remote helper事前導入、local/remote独立復旧鍵、loopback endpoint制約、AES-256-GCM envelope、OpenCode source-span patchをADRで確定したため設計上のExit条件を満たす。実機・sandbox Gate未通過の対象はread-onlyとする。

## Phase 1: Domain と Port（完了）

- project scaffold、domain models、errors、state machine
- application ports と fake adapters
- schema serialization/versioning
- acceptance criteria と test の traceability

成果物: domain schema、Port契約、fake Adapter、状態機械test。

Exit: OS/PySide6 なしのunit testでworkflowを表現できる。対応要件: FR-PLAN、FR-APPROVE、FR-AUDIT。

実装結果: immutable domain model、状態機械、schema envelope、application Port、fake Adapter、read-only診断ユースケースを追加し、OS/PySide6および実Ollamaに依存しないunit testでExit条件を確認した。

## Phase 2: Read-only Diagnostics（fixture/unit test完了、統合Gate待ち）

- process runner と secret redaction
- LocalHostAdapter、Linux probes
- Ollama/OpenCode Adapter の inspect 部分
- OpenSshHostAdapter と契約 test
- partial report、timeout、cancel

成果物: probe/parser、Local/SSH Host Adapter、診断report、redaction test。

Exit: Local/SSHの代表環境で設定変更なしに構造化reportを生成できる。対応要件: FR-HOST、FR-DIAG、FR-OLLAMA、FR-OPENCODE。

実装済み: allowlist付きprocess runner、実行中cancel、secret redaction、Linux system/memory/disk/GPU parser、Local/OpenSSH Host Adapter、Ollama API/systemd parser、OpenCode JSONC read-only parser、partial report。fixture/unit testは実OllamaやSSH接続なしで実施済み。

Local Gate完了: Ubuntu 26.04.1、Ollama 0.33.2 API/systemd、OpenCode 1.18.25複数provider JSONCをread-onlyで統合確認した。

SSH read-only Gate一部完了: alias `development`のUbuntu 26.04、OpenCode 1.18.18複数provider JSONC、Ollama未導入時の縮退を確認した。

`development`ではOpenSSH effective destination、known_hosts、実接続でネゴシエートされたED25519 host-key fingerprintの一致まで確認した。

未完了Gate: Debian 13での実コマンド差異、Ollama導入済みSSH先、host-key解決の自動化と変更検知test。実環境に対してはread-only診断だけを行い、設定変更・sudo・service操作は行わない。

## Phase 3: Optimization と Planning（完了）

- 3 profiles、typed Python Rule Engine
- versioned rule catalog と golden tests
- Change Planner、schema-aware edit、diff、conflict/precondition

成果物: 3 profiles、Rule catalog、golden fixture、Change Planner、masked diff。

Exit: fixturesから説明可能で決定論的なRecommendation/ChangeSetが得られる。対応要件: FR-PROFILE、FR-REC、FR-PLAN。

実装結果: 3 profile、typed Python catalog v1.0.0、version/接続/Agent compaction rule、明示的conflict、3 profile golden、report hash固定Plan生成、OpenCode既存scalar source-span Planner、Ollama専用drop-in Plannerを追加した。数値context/parallel/timeoutは検証済みboundsが注入されない限りChange化しないため、未検証値を「最適値」として提示しない。

## Phase 4: Safe Apply Core（完了）

- Backup Store と integrity
- user-level atomic file apply
- Validator、rollback、audit、fault injection
- PolicyKit/remote helper prototype、SSH passwordless/外部端末対話sudo、local+remote backup boundary

成果物: Backup Store、Executor、Validator、Rollback、helper protocol、recovery journal。

Exit: sandbox対象で成功・失敗・復元・復元失敗を安全に再現できる。対応要件: FR-BACKUP、FR-APPLY、FR-VALIDATE、FR-ROLLBACK、FR-AUDIT。

先行実装済み: Ptyxis/GNOME Terminal/x-terminal-emulator検出、argv分離、OpenSSH対話認証ControlMaster broker、0700 runtime directory、一時socket readiness確認、明示終了、timeout/cancel。`192.168.1.253`でパスワードをアプリへ渡さず認証し、Ollama導入済みSSH診断を`complete`まで確認した。

Safe Apply core実装済み: local sandbox向けBackup Store（16 MiB上限、0700/0600、manifest/content hash検証、厳格なschema/identity検査、再起動後の一覧再構築、30日/10世代保持、manual protection永続化）、同一targetのsource-span統合、before hash/path/symlink検査、fsync+atomic rename、file hash/OpenCode JSONC/Ollama専用systemd drop-in Validator、Ollama service/effective environment/APIとOpenCode再読込の実行後Validator、ApprovalRecordに束縛したCoordinator、redacted hash-chain audit log、atomic operation journal、before/after/unknown状態照合、逆順rollback、`RECOVERY_REQUIRED`終端。runtime validation失敗もrollbackへ接続した。実Ollama/OpenCode/systemd/SSH先は変更していない。

Closure結果: Secret Service positive、PolicyKit success/dismiss/deny、local/remote package lifecycle、転送中の実SSH切断、root journal evidence取得とread-only reconciliationをdisposable環境で完了した。sandboxでは成功・失敗・rollback・`RECOVERY_REQUIRED`を故障注入で再現し、実desktopではGate専用unitだけで特権/systemd境界を確認した。したがってPhase 4 Exitを満たす。実Ollama/OpenCode targetへのApply/rollbackは無断変更禁止のためExit条件に追加せず、未実施を維持する。

SSH切断後のread-only照合core実装: local journalとBackupManifestのoperation/plan/host/change-set/backup/manifest hash、manifest integrity、再接続先host ID/known-host fingerprintを検証してからremote `stat`でbefore/after/unknownを判定する。binding・identity不一致、再切断、cancelでは自動Apply/rollbackへ進まない。user staging転送中の実SSH切断と、canonical root evidence取得後の実remote target `unapplied`照合を検証済みである。

Remote root journal evidence境界実装: root journalを任意path読込せず、限定helperが返す1 MiB以下のcanonical evidenceへoperation/plan/host/fingerprint/change-set/backup/manifest/request/rollback hash、status、targets、remote journal hashを束縛する。root側は`/var/lib/llm-manager/journals/evidence`固定、0700/0600、root owner、非symlinkをdescriptorで検証する。OpenSSH Portはhelper互換性再検証後、固定`sudo -n -- ... read-journal-evidence <operation-id> <request-hash>`だけを実行し、検証済みevidenceを既存read-only reconcilerへ渡す。改ざん、別operation、切断、timeout、sudo不可ではremote targetを観測せずfail-closedにする。fake runnerとdisposable Ubuntu 26.04の実remote helper/SSH Gateを完了した。

Dual backup境界実装: local正本の作成・検証済み復元素材からremote recovery copyを作るportと、両copyの検証を集約するStoreを追加した。remote receiptへlocal manifest identity/hash、全item hash、host fingerprint、固定remote保存先、独立`remote_root` key reference、receipt hashを束縛する。remote作成・読込・receipt検証失敗時もlocal正本を保持しつつApply Gateを失敗させる。fake remoteに加え、disposable Ubuntu 26.04でSSH転送と実remote helperを検証した。

Remote recovery暗号化root backend実装: 検証済みplaintextを独立`remote_root`鍵のAES-256-GCM envelopeとして保存し、0700/0600、owner、固定logical path、symlink/path escape拒否、canonical receipt再読込、receipt/envelope/AAD/plaintext hash改ざん検出を行う。productionはrootかつ`/var/lib/llm-manager/backups`に固定し、alternate rootは明示sandboxだけを許す。disposable Ubuntu 26.04で実`/var/lib`配置・SSH Gateを完了した。

Remote recovery helper transport境界実装: user-only stagingとroot-only remote helperの間を、任意argvやshellを持たない`create_recovery_copy`専用Portとprotocol v1 canonical requestで分離した。request/receiptの双方でlocal manifest hash、backup/plan/change-set/host/fingerprint、全item hash、固定保存先、`remote_root` key referenceを照合する。転送切断、remote暗号化失敗、receipt取得失敗、再接続後receipt改ざんはlocal正本を保持してApply Gateをfail-closedにする。disposable Ubuntu 26.04でOpenSSH転送、remote helper、root key/backendと転送中の実切断Gateを完了した。

Remote recovery helper executor実装: root側でrequest ID/hashからuser stagingを固定導出し、0700 directory、0600 request/item、owner、regular file、16 MiB上限、完全なitem集合、content hashを再検証する。protocol requestへcreated/expires/protectedも束縛し、30日期限を固定してmanifestを再構築後、remote-root暗号化backendへ接続し、0600 canonical receiptをuser stagingへ公開する。replay result、別key reference、欠落/余剰/改ざんitemを拒否する。sandboxとpackaged remote helper/root keyの実Gateを完了した。

Remote helper CLI core実装: 固定subcommandは非root userの`user-stage-prepare/remove <derived-path>`と、rootの`invoke-recovery <request-id> <request-hash>`だけとする。root invocationは`SUDO_UID`からuser home/stagingを導出し、executorへ接続する。prepareはprivate directory/itemsを作り、cleanupは既知entryを全検査後だけ削除する。未知command/path、rootによるuser command、非root invoke、UID欠落、未知entryをstable resultで拒否する。別deb/wrapperのsandbox artifactと実配置/lifecycle Gateを完了した。

Remote helper production entrypoint実装: root `invoke-recovery`時だけfixed backup/key roots、root key provider、AES-GCM cipher、remote root backendをruntime factoryで構築する。非root/未知commandではbackend/key accessを開始しない。remote helper専用debは`python3 -I` wrapper、root-owned private runtime、canonical metadataだけを収め、local helper/PolicyKit/Secret Service/OpenSSH clientを混在させない。sandbox artifact検証に加え、disposable Ubuntu 26.04で実install、同一版reinstall、remove、purge、再installとremote protocol互換診断を完了した。Debian 13でもstock Python/cryptographyによるinstall、未知command fail closed、bytecode非生成、remove/purge/reinstallを完了した。

Remote root key provider実装: production key rootを`/var/lib/llm-manager/keys`へ固定し、key referenceごとの32-byte AES keyをO_EXCLで一度だけ生成する。directory 0700、key 0600、root owner、regular file、symlink、長さをloadごとに再検証し、不完全keyを自動置換しない。`remote_root` scopeだけを許し、backup/receipt rootとは分離する。alternate sandbox rootの単体テストとdisposable Ubuntu 26.04の実`/var/lib` Gateを完了した。

User-only SSH staging具体化: remote userの固定相対root `.local/state/llm-manager/remote-helper`配下へ、request ID/request hashから操作directoryを導出する。既存itemをhash付き固定名で先に0600転送し、canonical requestを最後に公開してからrequest ID/hashだけで限定helperを起動し、固定`result.json`を1 MiB上限で取得する。期限・改ざん・item hash・cancelをhelper起動前にも検査する。system `ssh`/`scp`の固定argv、OpenSSH alias/ControlPath、0600 local一時file、bounded downloadを実装し、root helper起動はpasswordless/外部端末sudo専用invokerへ分離した。実SSH staging/result回収/cleanupと転送中の実切断Gateを完了した。

Remote sudo invoker実装: system OpenSSHで固定`sudo -n -v`だけをpasswordless probeし、成功時は限定helperを非対話実行する。probe失敗時は外部端末の`ssh -t`内でsudo認証を行い、user stagingの固定result completionをbounded pollする。helper自身の失敗を認証失敗と誤認して再端末起動せず、cancel/timeout/terminal failureを分離する。fake runner/terminalに加え、disposable Ubuntu 26.04で外部端末sudo認証Gateを完了した。

Remote retention backend/helper境界実装: immutable receipt hashへ束縛したcanonical retention recordを0600で保存し、hostごと30日かつ直近10世代の未保護copyを古い順に削除する。protected copyと最後の1 copyは自動削除しない。canonical request/resultはrequest ID/hash、host ID/fingerprint、5分以下の期限、root評価時刻、removed/remaining IDs、completed/partial/failed/unknownを束縛する。requestはhelper起動前にlocal private immutable attemptへ保存し、remote resultはlocal 0700/0600 storeへ永続化してからstagingをcleanupする。切断・再起動後は同一identityのresultだけを回収し、pruneを再実行しない。実SSH/production retention/deletionと転送中切断Gateを完了した。

Dual-copy協調削除core/remote protocol実装: 5分期限のrequestへbackup/host/fingerprint/manifest hashを束縛し、remoteを先、localを後の固定順序で削除する。remote側は事前検証済みreceiptのhash、key reference、固定storage location、全item hashもcanonical protocolへ束縛し、user stagingのrequest ID/hashだけで限定`invoke-deletion`を起動する。canonical remote requestは変更前にlocal private immutable attemptへ保存する。削除後の切断でresultを観測できなければlocal正本とremote stagingを保持し、再起動後は同一request ID/hashのresultだけを回収してhelper replayを防ぐ。協調削除resultをlocalへimmutable保存した後だけstaging cleanupを行い、失敗はpendingとして再読込・cleanupだけを再試行する。fake境界統合まで完了し、実SSHとGUI UXは未実装である。

Backup一覧状態集約core実装: local manifest、remote retention record、local/remote retention run result、協調削除viewをbackup ID単位で集約し、copy presenceと`both_available/local_only/remote_only/both_deleted/unknown`、retention削除、cleanup pending、attentionを表示用immutable modelへ変換する。local retentionも削除前後をread-only再一覧してremoved/remainingを照合し、host/time/state/errorをcanonical hash付きresultへ束縛して0700/0600 local storeへimmutable保存する。片側削除失敗後のread-only reconciliationはsource deletion result hash、manifest hash、host/fingerprint、観測時刻、両copy presence/stateをcanonical resultへ束縛し、同じprivate metadata規則でimmutable保存する。協調削除はremote mutation前にcanonical manifest evidenceを保存し、限定reconciliation action serviceはlocal copy削除後だけこれへフォールバックする。evidence retention plannerはterminalかつattention不要のbundleだけを30日または11世代目以降の候補にし、protected/recovery-required/`orphan`/`missing_manifest`を自動候補にしない。sandbox executorは実行直前にplanと全bindingを再検証し、関連reconciliation result、manifest evidence、参照元deletion resultの順でfsync付き削除する。途中失敗は後続を止め、`completed/partial/failed`とremoved/remaining種別を返す。production配置とexecution result永続化は未実装である。永続evidence repositoryは最新resultとcleanup markerを安全に一覧へ自動ロードし、snapshotだけでは変更retryを許可しない。GUI接続はPhase 5で行う。

特権helper protocol実装: protocol v1のcanonical JSON、request hash、10分以下の期限、operation/plan/host/change-set束縛を追加した。operationは`atomic_replace`, `remove_created_file`, `restore_file`, `daemon_reload`, `restart_unit`の固定enumのみで、ファイル対象はLLM-Manager専用Ollama drop-in、unitは`ollama.service`だけを許可する。shell、argv、環境変数、任意pathをschemaとして受け取らず、未知field、改ざん、期限切れ、未来時刻、path/unit逸脱を拒否する。drop-in書込metadataは0644/root:rootに固定し、removeにもbefore hashを必須とする。PolicyKit policy、root-owned helper executable、system backendとGate専用unitによる実境界検証を完了した。

Helper staging実装: staging pathはrequest入力にせず`operation_id/item operation_id`から固定導出する。root/item directory 0700、content 0600、owner、regular file、symlink、16 MiB上限、request/staged hashをstage時とhelper側verify時に再検証する。既存itemの上書き、world-readable file、world-writable root、内容差替え、予期しないcleanup entryを拒否する。root-owned helper、PolicyKit policyとGate専用systemd操作の実境界検証を完了した。

Helper execution core実装: 実行直前にrequest期限/hash、対象before hash、staged content hashを再検証し、固定operationを宣言順にbackendへ渡す。stale targetは変更前に拒否し、write/reload等の失敗後は後続operationを`not_executed`として停止する。backendはprotocolで分離し、単体テストではsandbox fakeだけを使用している。

Local system helper backend実装: 論理targetを専用Ollama drop-inと完全一致させ、regular file/symlink/16 MiB/親directory安全性を再検査する。書込は0644/root:root、atomic rename、file/parent fsyncを行い、service操作は`/usr/bin/systemctl daemon-reload`と`/usr/bin/systemctl restart ollama.service`の固定argvだけを生成する。明示sandbox mode以外の代替rootを拒否し、単体テストでは一時rootとfake runnerだけを使用している。packaged executableとPolicyKit actionの配置はUbuntu 26.04で確認済みだが、実Ollama target/unit操作は禁止境界により未実施である。

Helper CLI/PolicyKit定義実装: CLI引数はoperation IDとrequest hashだけに限定し、local固定`pkexec`経路が設定する`PKEXEC_UID`からuser runtime staging pathを固定導出する。継承された`SUDO_UID`はlocal identityに利用しない。root実行、requestの0600/owner/regular file/1 MiB上限、operation identityを再検査し、結果はstable codeだけのcanonical JSONで返す。PolicyKit actionはactive sessionの`auth_admin`、固定`/usr/bin/llm-manager-helper`に限定した。Ubuntu 26.04 desktopでroot-owned配置と認証success/dismiss/denyを確認した。Debian 13ではLiveでGate専用action/unitのsuccessと明示deny、通常installしたpassword-backed GNOME sessionでdismiss exit 126とunit/marker無変更を確認し、全artifactをcleanupした。

Helper replay receipt実装: root-only receipt directoryへoperation IDを`O_EXCL`で実行前にclaimし、同一requestの再実行を`replayed_request`、異なるrequest hashによるID再利用を`operation_id_collision`として拒否する。receiptは0600、directoryは0700で、`executing`から`completed`または`failed`へterminal resultをatomic保存する。sandbox testでは成功・失敗・改ざん・CLI二重実行を再現している。

Local PolicyKit invoker実装: requestに必要な全contentをhash検証付きでstageした後、canonical requestを最後にimmutable stageし、`/usr/bin/pkexec /usr/bin/llm-manager-helper <operation-id> <request-hash>`の固定argvだけをrunnerへ渡す。helper結果は1 MiB以下のcanonical JSON、operation ID/kind/order/exit status一致を検証する。timeout、PolicyKit deny/dismiss、launch failure、helper failureをstable error codeへ分離した。単体テストはfake runnerのみで、実認証は起動していない。

Approved privileged apply境界実装: `ApprovalRecord.is_valid_for`へplan期限も追加し、plan/report/change-set/backup-policy/plaintext acknowledgement/plan期限/approval期限の一致をhelper request生成前に再検証する。MVPの単一Ollama専用drop-in root changeだけを`atomic_replace → daemon_reload → restart ollama.service`へ変換し、request期限をplan・approval・5分の最短値に束縛する。allowlist外path、非root/mixed/複数change、欠落restart/reloadをPolicyKit呼出し前に拒否する。

Privileged Safe Apply workflow実装: local root変更専用CoordinatorでBackup検証後だけhelper Applyを開始し、成功後にruntime validation、失敗時に別の期限付きhelper rollback requestを実行する。既存fileは`restore_file`、新規fileは`remove_created_file`を逆順生成し、その後`daemon_reload → restart ollama.service`を行う。write/reload/restart/runtime validationとrollback各段階のsandbox故障注入、`RECOVERY_REQUIRED`終端を追加した。manifestのchange-set hashと、approval/backup/manifest/request identityをhelper request・receipt対応hash・journalへ束縛した。実PolicyKit認証とsystemd操作は行っていない。

Local privileged境界統合test実装: root CoordinatorからLocalPolicyKitInvokerの固定argv、user staging、helper CLI、root-only replay receipt、DeclaredHelperExecutor、sandbox LocalSystemHelperBackendまでを一時directoryとfake service runnerで接続した。commit、runtime validation起因rollback、daemon-reload失敗起因rollbackについて、apply/rollbackが別receiptを持ちjournalのrequest hashと一致することを検証した。pkexec、実systemd、実設定は起動・変更していない。

Local deb先行Gate実装: Debian debhelper/dh-python構成、PolicyKit policy、manpage、root-owned固定helper wrapperを追加した。helper wrapperは`python3 -I`で起動し、pip console scriptによる特権導入を禁止する。binary debを一時copyでbuildし、artifact内のroot ownership、0755/0644 mode、isolated shebang、PolicyKit固定path、runtime dependencyを`verify-deb.sh`で検証した。Ubuntu 26.04 desktopでinstall/reinstall/remove/purge相当/reinstall/upgradeを完了し、PolicyKit dependencyを`polkitd`+`pkexec`へ修正した。Debian 13 stockにsupported minimumを合わせ、local/remote正式artifactのAPT simulation、Secret Service、PolicyKit success/deny、Gate専用systemd操作を完了した。

Helper compatibility診断・Plan Gate実装: local/remoteそれぞれのhelperとroot-owned canonical metadataの固定pathをread-onlyで調べ、root:root ownership、0755/0644 mode、非symlink、content hash、package名、package version、protocol versionを全て満たす場合だけ特権境界へ進める。remote probeはsystem OpenSSHの固定`stat`/bounded `cat`へ接続し、user staging開始前とroot helper起動直前に再検証する。missing、unsafe、invalid、incompatible、probe例外はfail-closedにし、不一致時はstaging commandを発行しない。実SSHでmissing/ready/remove後missing/reinstall後readyを確認した。

Apply時helper再検証実装: 診断・Plan後のhelper差替えや削除を信用せず、root workflowはBackup前とhelper起動直前に互換性を再検証する。Backup前の失敗は永続物を作らず、検証済みBackup後の失敗はBackupを保持して未変更で停止する。いずれもinvoker、pkexec、systemd操作へ到達しないことをsandbox fakeで確認した。

暗号化基盤の実装: `cryptography` AES-256-GCMによるversioned canonical envelope、item 16 MiB上限、12-byte random nonce、backup ID/host fingerprint/targetを束縛するAAD、key reference/scope検査、改ざん・scope取り違え検出を追加した。生鍵はenvelopeへ保存せず`BackupKeyProvider`から取得する。LocalBackupStoreのcreate/verify/reload/restoreへ統合し、暗号policy hashをPlan/Approvalへ束縛した。鍵provider不在時は平文fallbackせず停止する。SecretStorage adapterはdefault collection、属性検索、OS unlock prompt、32-byte master keyのcreate/reuse、競合時再読込、cancel/timeout/unavailable停止を実装した。Ubuntu 26.04とDebian 13 desktopでGate専用keyのcreate/reload/deleteを完了した。Debian 13 stockのPython 3.13.5、cryptography 43.0.0、SecretStorage 3.3.3で全338単体テストとlocal/remote package runtime Gateを通過した。

Backup設定実装: 一般配布buildは暗号化ON、明示的development buildはOFFを初回既定とし、保存済みユーザー選択が存在すればbuild既定で上書きしない。設定は0600、親directoryは0700、canonical schemaで保存する。暗号化OFFのApplyは`ApprovalRecord.plaintext_backup_acknowledged=true`がなければ拒否する。

## Phase 5: PySide6 GUI

- Hosts/Diagnose/Recommendations/Review/Results/Backup
- QThreadPool coordinator、progress、cancel、host lock
- accessibility、error UX、stale approval
- locale自動選択、言語切替、日本語/英語catalog、fallback/layout test

成果物: 6工程の画面、worker coordinator、状態遷移、GUI acceptance tests。

Exit: acceptance scenariosがGUI経由で完了し、UI threadがblockしない。対応要件: FR-APPROVEと全表示要件、AC-05、AC-09。

先行実装: Qt非依存のpresentation layerとして6工程の`GuiStep`、workflow status、immutable `GuiState`、`GuiPresenter`を追加した。host未選択、二重診断、report host不一致を拒否し、complete/partial/failed、cancel request、host/plan変更時の承認失効をheadless testで検証する。ja/en catalogは同一key集合を持ち、localeのlanguage部分を選択し、未対応・空localeを英語へfallbackする。QThreadPool境界は`QRunnable`、QObject signal、CancellationToken、host単位active lockを持つoptional adapterとし、PySide6不在時はstable `pyside6_unavailable`で停止する。最小Hosts/Diagnose widgetはprimary controlのobject/accessibility name、言語切替、background診断とRecommendations遷移を実装した。Ubuntu 26.04 disposable VMのPySide6 6.10.2 offscreen Gateでworker別thread、event-loop sentinel、result/cancel、window/language、Diagnose vertical sliceの4件を完了した。

Hosts/composition実装: `~/.ssh/config`とrelative `Include` globを1 MiB/128 files上限でread-only列挙し、literalかつAdapter契約に適合するaliasだけを重複排除してLocal候補の後へ表示する。wildcard、negation、unsafe aliasは候補化せず、missing configはLocalだけへ縮退する。host selectorはbusy中無効化し、選択IDをtask/reportへ束縛する。production compositionはLocal processを固定診断allowlist、SSH外側をsystem `ssh`だけへ限定し、未知hostをprocess前に拒否する。main workstationの実Local read-only taskは`partial`、host binding成功、Ollama観測あり、PATH外OpenCodeは個別失敗として確認した。

OpenSSH identity実装: 固定`ssh -G -- <alias>`のeffective hostname/port/HostKeyAliasを取得後、`BatchMode=yes`、`StrictHostKeyChecking=yes`、`UpdateHostKeys=no`、固定remote `true`のverbose接続から一意な`Server host key` SHA-256 fingerprintを得る。exit 0、またはOpenSSHがknown-host一致を明示して認証だけ未完了となった場合にidentityを確定する。alias、config、timeout、host-key未確認、fingerprint欠落/複数/不正は診断前にfail closedとし、検証値だけを`OpenSshHostAdapter`へ注入する。LF/CRLF debug outputを検証した。実`development` read-only Gateは接続timeoutとなり、identity/reportを生成せず安全に停止した。

ControlMaster GUI composition実装: strict known_hostsの直接probeが一意なSHA-256 fingerprintとOpenSSHのknown-host一致を確認したうえで認証未完了となった場合だけ、利用可能な外部terminalでOpenSSH aliasをそのまま使う一時ControlMasterへfallbackする。これによりUser、Port、IdentityFile、Agent、ProxyJump等はsystem OpenSSH configへ委譲する。host-key変更、未知key、config異常、timeoutはterminal起動前にfail closedとする。masterのsocket readiness成功後だけ、事前検証したfingerprintと同socketへ診断を束縛し、sessionは成功、失敗、cancelの全経路でcontrol `exit`する。実`llm-manager-gate`では外部Ptyxis master、同socket上のproduction read-only診断が`complete`、host/fingerprint binding成功、failed probe 0、終了後runtime artifact 0となった。

Recommendations/Review preview vertical slice実装: 診断reportから既存catalog version固定RuleEngineで期限付きOptimizationPlanを生成し、Balanced/Coding/Agent切替ごとに再評価する。setting/current/recommended、severity、actionable/read-only、理由、影響を一覧表示し、秘密名の設定値は表示前にredactする。ja/en catalogへprofile、summary、rule説明を追加し、言語切替時にprofile名と既存一覧を即時再描画する。actionableかつ非conflictの推奨だけを明示チェック可能とし、重複・未知・read-only IDを拒否してsorted selected IDsへ束縛する。Reviewは選択内容と「preview only・実行可能ChangeSet未生成」を明示し、自動Applyや承認へ進まない。Ubuntu 26.04/PySide6 6.10.2 offscreen GateでAgent推奨2件、英日再描画、1件選択、Review遷移を含む9件が成功した。read-only再取得、実diff生成、承認接続は後続とする。

ChangeSet planning core/GUI接続実装: 選択済みOptimizationPlanを元DiagnosticReportのID/hash/期限へ再束縛し、選択IDがactionable・非conflict・active OpenCode configだけを対象とすることを検証する。hostを再identifyしてID/kind/fingerprint一致後にactive configをread-onlyで最大1 MiB・strict UTF-8として再取得し、既存OpenCode plannerからsource span、before hash、masked diffを持つChangeSetを生成する。stale report/plan、host identity変更、欠落・不正選択、target不一致、encoding異常、空ChangeSetはfail closedとする。Local/SSH compositionを同じhost lockとCancellationTokenのQThreadPool workerへ接続し、生成中はhost/profile/selectionを固定する。SSHは診断と同じstrict identity・外部terminal ControlMaster境界を再利用し、全終了経路でsessionを閉じる。成功時だけtarget、masked diff、root/restart要否をReviewへ表示し、失敗時はChangeSetなしでstable errorを残す。Ubuntu 26.04/PySide6 6.10.2 offscreen Gateは関連25件に成功した。明示承認とstale失効、Apply接続は後続とする。

Review明示承認/stale失効実装: ChangeSet生成成功後だけ承認checkboxを有効にし、表示中の`change_set.content_hash`とplan期限へ承認状態を束縛する。checkbox解除は即時取消、期限到達はsingle-shot timerと承認時の再検査の双方で`stale_plan`へ失効する。host変更と再診断はworkflow stateを初期化し、profile/selection変更はChangeSet、hash、承認、timerを同時に破棄する。staleまたは生成失敗時はdiffと承認controlを無効化する。Ubuntu 26.04/PySide6 6.10.2 offscreen Gateは自動期限切れを含む関連20件に成功した。ApprovalRecord生成、Apply前のbackup policy確認、Results接続は後続とする。

Apply前準備実装: Review checkboxとは別の明示操作でだけ期限付き`ApprovalRecord`を生成し、plan/report/change-set/backup-policy hash、GUI実行user、平文acknowledgement、planと5分の短い方の期限へ束縛する。一般配布は暗号化ON、`LLM_MANAGER_DEVELOPMENT_MODE=1`を明示したsource開発実行だけOFFを初回既定とし、既存のprivate backup settingsがあれば優先する。Reviewに暗号化・30日/10世代保持を表示し、暗号化OFFでは独立した平文risk checkboxを満たすまで準備できない。有効なrecordだけResultsへ渡し「Apply未開始」を明示する。Ubuntu 26.04/PySide6 6.10.2 offscreen Gateは関連24件に成功した。実Apply、backup作成、PolicyKit/sudoは未接続である。

## Phase 6: Hardening と MVP Release

- 対応環境 matrix の実機検証
- security/privacy review
- ソース起動手順、deb packaging、upgrade/uninstall、backup retention、recovery guide
- performance、long-running Agent scenario、SSH disconnect tests

Exit: Definition of Done と release checklist を満たす。

開発途中のMVP検証はソース起動を許容する。一般ユーザーへMVPを配布するrelease gateではdebのinstall/upgrade/uninstall、依存関係、PolicyKit/helper配置を検証する。

## Post-MVP

優先候補:

1. GPU/runtime telemetry の強化と履歴比較
2. Codex / Claude Code / OpenClaw Client Adapter
3. 複数ホスト orchestration
4. 明示的 benchmark use case
5. llama.cpp / vLLM Runtime Adapter
6. 制約付き YAML rule catalog と署名済み更新
7. CLI frontend
8. Rust/Tauri への段階的 UI または core 移行

## リスクと検証順

最大のリスクは設定 schema の版差、権限境界、SSH 切断時の整合性、復元可能性である。GUI の作り込みより前に、fake/sandbox で ChangeSet と rollback の状態機械を検証する。具体的な性能閾値は根拠となる仕様・実測が揃うまで固定しない。

## 継続的な設計管理

重要判断は `docs/adr/` に ADR として追加する。最低限、OpenSSH 採用、Rule format、Qt concurrency、privilege helper、backup placement、supported version policy を記録対象とする。要件 ID、test ID、release checklist を相互参照可能にする。
