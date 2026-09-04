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

## Phase 5: PySide6 GUI（完了）

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

Sandbox/fake Apply Results実装: `OptimizationPlan + ApprovalRecord`をimmutable入力とする注入可能なtask factoryを、診断・ChangeSet生成と同じhost lock、QThreadPool、CancellationTokenへ接続した。Resultsはrunning、committed、rolled_back、recovery_required、worker error/cancelを構造化状態から表示し、UIはinfrastructureへ依存しない。production compositionはtask factoryを渡さないため実行buttonを無効化し「Apply未接続」を明示する。Ubuntu 26.04/PySide6 6.10.2 offscreen Gateは25件中24件成功、PySide6存在時のnegative test 1件skipで完了した。実backup/file mutation/PolicyKit/sudoは行っていない。

Production Apply接続監査: report/plan/host/change-set bindingと全changeのroot要否から`local_user`、`local_root`、`ssh_user`、`ssh_root`を決定論的に分類し、混在privilegeを拒否する。4経路とも現時点ではproduction GUIへ接続せず、それぞれlocal store/executor composition、PolicyKit workflow composition、SSH user atomic write/backup transport、remote privileged Apply helper protocolの不足を固定理由としてResultsへ表示する。既存remote sudo helperのallowlistはrecovery/retention/deletionだけでありApplyへ流用しない。次はまずlocal user経路のprivate production state root、Secret Service、audit/journal、runtime validator compositionをsandboxで閉じる。

Local user Apply composition Gate: non-root local OpenCode ChangeSetだけを許可するtask factoryを追加し、対象をcanonicalな`$XDG_CONFIG_HOME/opencode`（fallback `~/.config/opencode`）配下へ限定した。SSH host、root change、範囲外target、symlink application rootをI/O開始前に拒否し、実行直前にもrootを再検証する。private `$XDG_STATE_HOME/llm-manager`（fallback `~/.local/state/llm-manager`）は所有者と0700を検証し、暗号化時だけSecret Service providerを遅延生成してAES-GCM local backup、atomic Apply、file/runtime validation、hash-chain audit、operation journal、rollbackを一つのcompositionへ束縛した。一時rootのencrypted success/unsafe-root negative sandbox Gateに加え、Ubuntu 26.04 password-backed GNOME sessionで実Secret Service keyの作成、暗号化Apply、key cleanupまで1件成功した。production GUIへの接続と実OpenCode target mutationは未実施である。次はlocal user routeだけを選択的にGUIへ接続し、他の3 routeをfail closedに保つ。

Selective production Apply接続: route availabilityを完成済みrouteの明示集合へ変更し、既定の空集合はfail closedを維持する。production entrypointは`LocalUserApplyTaskFactory`と`local_user`だけをGUIへ注入し、実行buttonはfactoryとroute availabilityの双方が揃う場合だけ有効になる。local root/SSH user/SSH rootは個別理由を表示して無効のままである。Ubuntu 26.04/PySide6 6.10.2 offscreen Gateでentrypoint、4 route分類、英日catalog、実Qtのlocal root無効→local user有効を含む14件が成功した。Gateでは実設定を変更していない。次は一時config/state rootを使うGUI→local user composition vertical sliceである。

Local user GUI Apply vertical slice: 承認済みrecordからResultsの明示Apply操作、host lock付きQt worker、実`LocalUserApplyTaskFactory`、AES-GCM backup、atomic Apply、validation、audit/journal、`committed`表示を一続きにした。Ubuntu 26.04/PySide6 6.10.2で`/tmp`内の一時config/state rootだけを変更する1件が0.114秒で成功した。Gate専用memory keyを使い、実Secret Serviceと実OpenCode設定は変更していない。次はvalidation failure rollbackと`RECOVERY_REQUIRED`の実composition GUI表示を故障注入で検証する。

Local user GUI failure outcomes: production既定を変えずにruntime validatorとbackup storeをGate用に差し替えられるcomposition seamを追加した。Ubuntu 26.04/PySide6 6.10.2で一時configへのApply後にruntime validation失敗を注入し、暗号化backupから元内容へ復元してGUIへ`rolled_back`を表示した。別caseではrestore failureも注入し、変更後内容を残してGUIへ`recovery_required`を表示した。両caseを含む1件が0.087秒で成功した。次はBackup/Rollback画面のread-only inventoryと永続結果表示を監査する。

Backup/Rollback read-only UI slice: 注入可能なinventory taskをhost lock付きQt workerへ接続し、初期表示ではI/Oを行わず明示「再読込」でだけ実行する。backup ID、dual-copy state、local/remote presence、manual protection、attention、coreが算出済みのallowed action名を一覧表示するが、restore/rollback/delete/cleanupを開始するcontrolは設けない。host変更では旧一覧を破棄し、英日再描画はloaderを再実行しない。Ubuntu 26.04/PySide6 6.10.2 Gate 1件が0.054秒で成功した。production inventory factoryは未接続であり、次はlocal manifest/journalのstrict read-only compositionを構築する。

Local production inventory: 互換list APIとは別にstrict manifest/journal列挙を追加し、未知entry、symlink、owner/mode不一致、改ざん、host/storage/target root不一致を黙って除外せずrefresh全体で拒否する。共通backup/operation IDでmanifestとterminal journalを結合し、`committed`/`rolled_back`/`recovery_required`または`backup_only`、presence、protection、attentionを表示する。空stateはdirectoryを作らず空一覧とし、SSH hostはlocal loaderへ渡さない。暗号本文を復号せずSecret Serviceを起動しない。Ubuntu 26.04/PySide6 6.10.2でrestart/tamper/empty/SSH分離/entrypoint/Qtを含む5件が0.040秒で成功した。次はSSH production inventory compositionを監査する。

SSH inventory監査: 現行のroot journal readは既知operation/request hashに束縛された単一evidence取得だけで、backup ID列挙ではない。remote retention一覧も明示prune requestのroot helper内部照合でありGUI用read-only OpenSSH portではない。SSH production inventoryの接続には新しい固定helper commandとPolicyKit/sudo相当の権限・identity/fingerprint binding・実SSH Gateが必要になるため、Phase 5で安全境界を暗黙に拡張せずfail closedを維持する。次はlocal restore previewと明示承認境界を設計し、実mutationは未接続に保つ。

Local restore preview core: strict manifestからhost/backup/manifest hash、時刻、protection、target path・存在有無・SHA-256・modeだけをcanonical preview hashへ束縛するmetadata-only modelを追加した。本文復号、Secret Service、target読込、mutationは行わない。独立restore approvalは明示review、actor、exact preview、最長5分へ束縛し、tamper・別backup・期限切れを拒否する。sandbox 6件が成功した。次はQt表示とcheckboxの失効条件を接続する。

Qt restore preview: inventory選択からworkerでmetadata-only previewを取得し、英日表示と独立restore承認checkboxへ接続した。host変更、refresh、backup選択変更はpreview/承認を失効させ、言語変更だけでは再取得しない。restore mutation controlは存在しない。Ubuntu 26.04/PySide6 6.10.2でruntime/accessibility/import/i18nの9件が0.043秒で成功し、1件はPySide存在時の期待skipだった。次はpreview expiry timerを実Qtで検証する。

Restore preview expiry: 150 ms previewを使うQt runtime Gateで、承認後の期限到達によりcheckboxが自動解除・無効化され、previewを破棄してstable `stale_restore_preview`を表示することを確認した。Ubuntu 26.04/PySide6 6.10.2で1件が0.192秒で成功した。次は実行直前manifest/approval/target再検証契約を構築し、restore mutationは未接続に保つ。

Local restore preflight: 承認済みpreviewから直接restoreせず、実行直前にstrict manifestを再列挙してcanonical preview、approval期限、host/backup/manifest、protection、全target metadataとallowlistを再検証する。成功時も本文やmanifestではなく、approval/actor/hash/target/最短expiryをcanonical hashへ束縛した短命authorizationだけを返す。tamper、manifest変更、approval mismatch、cancelではfail closedとし、sandbox 9件が0.007秒で成功した。次はexecutor側の再検証・journal/audit・atomicity契約を設計する。

Sandbox local restore executor: 複数fileを一般filesystem上で真にatomicにできないため、最初の境界を単一local user targetに限定した。preflight時の現在target存在/hashもauthorizationへ束縛し、executorは復号前後にauthorization、strict manifest、target一覧、現在状態を再照合してからatomic replaceまたは単一unlink+directory fsyncを行う。変更・複数target・cancelはmutation前に拒否する。sandbox 6件が0.005秒で成功した。journal/audit、immutable replay防止、production/GUI compositionは未接続であり、次にこれらを構築する。

Restore execution evidence: authorization hashごとのattemptをmutation前にimmutable保存して再利用を拒否し、開始/完了auditと別immutable result evidenceへ接続した。restart時にcanonical/identity/hash/owner/mode/symlink/sizeを検証する。attemptまたは開始audit失敗はmutationせず、開始audit失敗でもattemptを保持して暗黙retryしない。commit後audit失敗は`UNKNOWN`、result保存失敗は生成済み`COMMITTED` evidenceを専用errorへ公開して未変更と推測しない。fault injectionを含むfocused 12件が成功した。次はstrict全entry一覧とattempt-only状態のread-only表示である。

Restore execution restart inventory: store全entryをstrict検証し、未知entry、symlink、metadata/canonical/hash/filename/binding不一致、orphan resultを一覧全体で拒否する。attempt-onlyはattentionとして既存local inventoryへ結合し、restore stateを英日表示するが自動retry actionは追加しない。restore evidenceだけのbackup IDも表示対象にする。Ubuntu 26.04/PySide6 6.10.2でQt/restart/tamper/fault injectionを含む12件が0.091秒で成功した。次はproduction composition可否監査である。

Local user restore production composition: local hostと単一OpenCode config targetに限定し、既存Secret Service provider、strict preflight、復号前後のtarget再検証、分離した0700/0600 execution store、hash-chain auditを一つのfactoryへ束ねた。attempt保存と開始auditより前にmutationせず、失敗・attempt-only・UNKNOWNから自動retryしない。sandbox production-root overrideで暗号化restore、外部変更拒否、immutable replay拒否をGateした。GUI実行controlと実config mutationは未接続を維持する。

Local restore desktop Gate: Ubuntu 26.04のログイン済みdesktop sessionで実Secret ServiceとGate専用key、一時config/stateを使い、暗号化backupからproduction factoryで単一targetを復元した。COMMITTED evidence/audit、暗号化envelope、key cleanupを確認し、1件が0.080秒で成功した。実OpenCode設定は変更していない。次はQt実行境界の失効・二重実行防止監査である。

Qt restore execution boundary: authorizationをQt stateへ保持せず、exact preview/approvalを注入taskへ渡して単一worker内でpreflightからexecutionまで行う。実行中はhost、inventory refresh、approval、runをロックし、double clickを1回に限定する。完了・失敗・cancelでpreview/approvalを消費し、同じreviewから再実行できない。production `main()`はrestore taskを注入せずfail closedを維持する。Ubuntu 26.04/PySide6 6.10.2で1件が0.114秒で成功した。次はproduction公開可否と実行結果表示・再読込境界の監査である。

Qt restore result evidence: production taskは正常COMMITTEDだけでなく、永続済みFAILED/UNKNOWNと専用persistence errorが公開するevidenceをbounded resultへ変換する。Qtは`committed/failed/unknown`、error、persistedをそのまま表示し、未知stateやevidence不在を成功と推測しない。結果後はpreview/approvalを消費し、明示inventory refreshまで再実行しない。Ubuntu 26.04/PySide6 6.10.2でworker lockと全result state表示の2件が成功した。production `main()`へのrestore接続は引き続き未実施である。

Local restore explicit refresh and production publication: sandboxの実backup/journal、production inventory/restore factory、Qt workerをend-to-end接続した。COMMITTED直後は旧inventoryをmutation結果として自動更新せず、明示refresh後だけstrict execution storeから`restore: committed`、attention falseを表示し、同じapprovalからrunを再有効化しない。Ubuntu 26.04/PySide6 6.10.2で1件が0.143秒で成功した。local user単一OpenCode target経路の全境界が閉じたためproduction `main()`へrestore taskを接続した。local root・SSH restoreは未接続である。

Restore route closure audit: 手動restoreをApply失敗時の自動rollbackから分離し、`local_user`、`local_root`、`ssh_user`、`ssh_root`のproduction可用性を独立してfail closed評価する。完成済みlocal userだけをproduction entrypointで有効化した。local rootはprivileged inventory/restore protocol、SSH user/rootは固定read-only inventory、fingerprint binding、atomic restore、journal reconciliationが不足するため、既存recovery/retention helperを流用しない。Backup/Restore画面はSSH選択時にI/O前から固定理由を英日表示し、再読込を無効化する。次はPhase 5全体のDoD closure auditで残項目を分類する。

Closure audit: 6工程、AC-05のReview表示、AC-09のQt非blocking/cancel/終端状態、AC-10の依存境界、AC-15の英日/fallback、local user Apply/restoreのproduction vertical sliceを確認し、Phase 5 Exitを満たした。local root・SSH user/root mutation、正式GUI deb、最終実機matrix、security/recovery文書、performance・長時間Agent・実display/layout・SSH切断のGUI acceptanceはMVP release blockerまたはPhase 6 hardeningとして明示的に引き継ぐ。詳細は[Phase 5 closure audit](validation/phase5-closure-audit-2026-09-04.md)を参照する。

## Phase 6: Hardening と MVP Release

- local root・SSH user/rootのproduction Apply/手動restore経路を安全な固定protocolと実機Gateで完成
- 対応環境 matrix の実機検証
- security/privacy review
- ソース起動手順、deb packaging、upgrade/uninstall、backup retention、recovery guide
- performance、long-running Agent scenario、SSH disconnect tests

Exit: Definition of Done と release checklist を満たす。

開発途中のMVP検証はソース起動を許容する。一般ユーザーへMVPを配布するrelease gateではdebのinstall/upgrade/uninstall、依存関係、PolicyKit/helper配置を検証する。

Local root planning boundary: local root production Apply監査で、GUI planningがOpenCode専用でOllama root ChangeSetへ到達不能なことを確認した。最初のsliceとして、plan/report/selection/host identityを再検証し、互換local helperをread-only再probeした後だけ固定Ollama drop-inをbounded readしてbefore hash付きChangeSetを生成するapplication serviceを追加した。既存fileなし、host/helper/target変更、非root selectionを含むsandbox 4件に成功した。local root routeはまだ公開せず、次はproduction診断へのhelper capabilityとtarget別planning factoryを接続する。

Local root diagnosis/planning composition: production local診断へ同梱helperのpackage/version/protocol/owner/mode probeを接続し、reportの`can_elevate`をread-only evidenceから設定する。SSH診断へlocal probeは渡さない。planning factoryは選択targetをI/O前に分類し、local Ollamaだけをroot planner、OpenCodeを既存plannerへ渡す。混在targetとSSH root planningは接続・terminal起動前に拒否する。関連31件が成功した。次はlocal root Apply task factoryを構成し、availability公開前にsandbox GUI Results Gateを完了する。

Local root Apply composition: local/root-only ChangeSetをprivate user state、Secret Service backup、固定systemd allowlist、user staging、pkexec-only runner、helper二重readiness、runtime validation、journal、redacted audit、別rollback requestへ束ねるtask factoryを追加した。local user/root routerはmixed privilegeを拒否する。privileged coordinatorのaudit portをapproved/backup/commit/rollback終端へ接続した。sandbox compositionと既存PolicyKit coreを含むfocused 18件が成功した。production entrypointへrouterは注入したが`local_root` availabilityは未公開である。次はUbuntu 26.04/PySide6 sandbox GUI Results Gateで全終端とdeny/cancelを検証する。

SSH user fixed Apply protocol boundary: local rootは実装済みcompositionを保ったまま、根拠あるactionable Ollama ruleが確定するまでfail closedとする。SSH userについては既存のdiagnosis→recommendation→fresh read→diff経路の後段として、unprivileged remote helperに`user-apply`を追加した。canonical requestはhost fingerprint、plan/change set、backup/local manifest、固定OpenCode target、before/after hash、短いexpiryを束縛し、payloadをrequest-last staging identityで照合してatomic write後のhashをimmutable resultへ返す。targetはremote home配下の3つのOpenCode global config名だけで、root実行、symlink、owner不一致、stale target、余分なpayloadをmutation前に拒否する。sandbox 4件が成功した。transport、dual-copy backup、disconnect reconciliation、rollback/runtime validation、GUI compositionは未接続のため`ssh_user` availabilityはfail closedを維持する。次は固定OpenSSH transportとlocal/remote backup verificationをこのprotocolへ接続する。

SSH user fixed OpenSSH Apply transport: recovery用sudo invokerと型境界を分けたuser Apply staging portを追加した。既存のsystem `ssh`/`scp` runnerとControlMaster socketを使い、payload-first/request-lastでprivate stagingへ転送し、固定helper argvだけを実行してbounded resultを取得する。resultはrequest ID/hash、host ID/fingerprint、target、before/after hashの完全一致を要求する。切断後は同一immutable requestのresultだけをread-only再取得し、Applyを自動retryしない。focused 12件が成功した。dual-copy backup、rollback/runtime validation、journal/audit、GUI compositionは未接続なのでfail closedを維持する。次はremote snapshotからlocal authoritative backupを生成し、root-owned remote recovery copyとともにApply前検証する。

SSH remote snapshot local backup: SSH host ID/fingerprintをbackup直前に再確認し、exact target allowlist、stat→bounded read→statのmetadata/hash一致、ChangeSet before hashを満たすremote snapshotだけをlocal authoritative storeへ渡すadapterを追加した。`LocalBackupStore.create_captured`は取得済みcontent/metadata/target集合を再検証してから既存AES-GCM envelope、canonical manifest、verify/restore-items経路へ保存する。snapshot取得中の変更、host/target差替え、hash不一致はbackup directory作成前に拒否する。remote stagingはuser-ownedだが、恒久remote recovery copyと独立鍵はADR-0009どおりroot-ownedを維持する。次はこのadapterを既存`DualCopyPrivilegedBackupStore`とremote recovery helperへ束縛し、両copy検証後だけApply可能にする。

SSH user dual-copy preparation: exact report/plan/approval、SSH fingerprint、単一allowlist済みnon-root targetを再検証し、local captured storeと既存root-owned remote recovery storeの全verification成功後だけ、local正本からpayloadとmanifest-bound canonical Apply requestを生成するmutation-free serviceを追加した。片側copy失敗ではrestore-items/request生成へ進まない。sandboxの実local manifest＋remote AES-GCM recovery storeを通し、remote key scopeが`remote_root`であることも含むfocused 4件が成功した。serviceはApply transportを持たないため、rollback protocol完成前のmutationは構造的に不能である。次はmanifest/request-bound SSH user rollbackとApply/validate/rollback coordinatorを構築する。

SSH user fixed rollback protocol/transport: Apply request hash、plan/change set、backup/local manifest、host/fingerprint、target、期待する現在after hash、元の存在/hash/mode、expiryをcanonical requestへ束縛するunprivileged `user-rollback` helperを追加した。stale targetと不正payloadをmutation前に拒否し、既存fileは元modeでatomic replace、Applyが作成したfileは単一unlink＋directory fsyncで戻す。OpenSSH transportはpayload-first/request-last、固定argv、bounded result完全照合を行い、切断後は同一resultのread-only再取得だけを許す。focused 11件が成功した。次はmanifestからrollback requestを生成し、Apply/runtime validation/rollback/journal/audit coordinatorへ接続する。

Local root Qt Gate: ユーザーが導入したqemu guest agent経由で既存Ubuntu 26.04 VMへartifactを転送し、PySide6 6.10.2上のQt workerからfake helper付き実compositionを実行した。COMMITTED、audit、journal、helper二重readinessを0.195秒で確認し、artifact/serverをcleanupした。PolicyKit deny/helper launch failureはmutation未開始として再度helperを起動せず、audit/journalをterminalへ閉じるよう修正した。default rule catalogからroot Ollama recommendationを生成する経路の監査が残るため、availabilityは未公開を維持する。

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
