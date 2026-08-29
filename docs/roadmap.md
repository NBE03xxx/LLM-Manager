# ロードマップ

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

## Phase 4: Safe Apply Core（進行中）

- Backup Store と integrity
- user-level atomic file apply
- Validator、rollback、audit、fault injection
- PolicyKit/remote helper prototype、SSH passwordless/外部端末対話sudo、local+remote backup boundary

成果物: Backup Store、Executor、Validator、Rollback、helper protocol、recovery journal。

Exit: sandbox対象で成功・失敗・復元・復元失敗を安全に再現できる。対応要件: FR-BACKUP、FR-APPLY、FR-VALIDATE、FR-ROLLBACK、FR-AUDIT。

先行実装済み: Ptyxis/GNOME Terminal/x-terminal-emulator検出、argv分離、OpenSSH対話認証ControlMaster broker、0700 runtime directory、一時socket readiness確認、明示終了、timeout/cancel。`192.168.1.253`でパスワードをアプリへ渡さず認証し、Ollama導入済みSSH診断を`complete`まで確認した。

Safe Apply core実装済み: local sandbox向けBackup Store（16 MiB上限、0700/0600、manifest/content hash検証、厳格なschema/identity検査、再起動後の一覧再構築、30日/10世代保持、manual protection永続化）、同一targetのsource-span統合、before hash/path/symlink検査、fsync+atomic rename、file hash/OpenCode JSONC/Ollama専用systemd drop-in Validator、Ollama service/effective environment/APIとOpenCode再読込の実行後Validator、ApprovalRecordに束縛したCoordinator、redacted hash-chain audit log、atomic operation journal、before/after/unknown状態照合、逆順rollback、`RECOVERY_REQUIRED`終端。runtime validation失敗もrollbackへ接続した。実Ollama/OpenCode/systemd/SSH先は変更していない。

残作業: Secret Service実desktop Gate、remote復旧copy、PolicyKit/remote helperの実環境integration Gate、remote journalとのSSH切断統合。local root変更のdaemon-reload/restartはsandbox fake workflowまで完了し、local helper同梱debはsandbox build/artifact検査まで完了した。実install、実PolicyKit、実systemd操作はdisposable OS Gateまで行わない。これらが完了するまでPhase 4 Exitは未達とする。

SSH切断後のread-only照合core実装: local journalとBackupManifestのoperation/plan/host/change-set/backup/manifest hash、manifest integrity、再接続先host ID/known-host fingerprintを検証してからremote `stat`でbefore/after/unknownを判定する。binding・identity不一致、再切断、cancelでは自動Apply/rollbackへ進まない。fake HostPortでのみ検証済みで、実SSH切断integrationは引き続き未完了である。

Remote root journal evidence境界実装: root journalを任意path読込せず、限定helperが返す1 MiB以下のcanonical evidenceへoperation/plan/host/fingerprint/change-set/backup/manifest/request/rollback hash、status、targets、remote journal hashを束縛する。root側は`/var/lib/llm-manager/journals/evidence`固定、0700/0600、root owner、非symlinkをdescriptorで検証する。OpenSSH Portはhelper互換性再検証後、固定`sudo -n -- ... read-journal-evidence <operation-id> <request-hash>`だけを実行し、検証済みevidenceを既存read-only reconcilerへ渡す。改ざん、別operation、切断、timeout、sudo不可ではremote targetを観測せずfail-closedにする。fake runnerまで完了し、実remote helper/SSH Gateは未実施である。

Dual backup境界実装: local正本の作成・検証済み復元素材からremote recovery copyを作るportと、両copyの検証を集約するStoreを追加した。remote receiptへlocal manifest identity/hash、全item hash、host fingerprint、固定remote保存先、独立`remote_root` key reference、receipt hashを束縛する。remote作成・読込・receipt検証失敗時もlocal正本を保持しつつApply Gateを失敗させる。境界はfake remoteで検証済みであり、SSH転送と実remote helperへの接続は未実装である。

Remote recovery暗号化root backend実装: 検証済みplaintextを独立`remote_root`鍵のAES-256-GCM envelopeとして保存し、0700/0600、owner、固定logical path、symlink/path escape拒否、canonical receipt再読込、receipt/envelope/AAD/plaintext hash改ざん検出を行う。productionはrootかつ`/var/lib/llm-manager/backups`に固定し、alternate rootは明示sandboxだけを許す。実`/var/lib`配置・SSH Gateは未実施である。

Remote recovery helper transport境界実装: user-only stagingとroot-only remote helperの間を、任意argvやshellを持たない`create_recovery_copy`専用Portとprotocol v1 canonical requestで分離した。request/receiptの双方でlocal manifest hash、backup/plan/change-set/host/fingerprint、全item hash、固定保存先、`remote_root` key referenceを照合する。転送切断、remote暗号化失敗、receipt取得失敗、再接続後receipt改ざんはlocal正本を保持してApply Gateをfail-closedにする。sandbox/fakeのみであり、OpenSSH転送、remote helper executable、root key配置は未実装である。

Remote recovery helper executor実装: root側でrequest ID/hashからuser stagingを固定導出し、0700 directory、0600 request/item、owner、regular file、16 MiB上限、完全なitem集合、content hashを再検証する。protocol requestへcreated/expires/protectedも束縛し、30日期限を固定してmanifestを再構築後、sandbox remote-root暗号化backendへ接続し、0600 canonical receiptをuser stagingへ公開する。replay result、別key reference、欠落/余剰/改ざんitemを拒否する。sandbox executorのみで、packaged remote helper executableと実root key配置は未実装である。

Remote helper CLI core実装: 固定subcommandは非root userの`user-stage-prepare/remove <derived-path>`と、rootの`invoke-recovery <request-id> <request-hash>`だけとする。root invocationは`SUDO_UID`からuser home/stagingを導出し、executorへ接続する。prepareはprivate directory/itemsを作り、cleanupは既知entryを全検査後だけ削除する。未知command/path、rootによるuser command、非root invoke、UID欠落、未知entryをstable resultで拒否する。別deb/wrapperのsandbox artifact Gateまで完了し、実配置は未実施である。

Remote helper production entrypoint実装: root `invoke-recovery`時だけfixed backup/key roots、root key provider、AES-GCM cipher、remote root backendをruntime factoryで構築する。非root/未知commandではbackend/key accessを開始しない。remote helper専用debは`python3 -I` wrapper、root-owned private runtime、canonical metadataだけを収め、local helper/PolicyKit/Secret Service/OpenSSH clientを混在させない。sandbox buildでownership、mode、dependency、isolated import、bytecode cache不在を検証する。実install/upgrade/remove/purgeとremote protocol互換診断は未実施である。

Remote root key provider実装: production key rootを`/var/lib/llm-manager/keys`へ固定し、key referenceごとの32-byte AES keyをO_EXCLで一度だけ生成する。directory 0700、key 0600、root owner、regular file、symlink、長さをloadごとに再検証し、不完全keyを自動置換しない。`remote_root` scopeだけを許し、backup/receipt rootとは分離する。単体テストはalternate sandbox rootのみで、実`/var/lib`への生成・配置Gateは未実施である。

User-only SSH staging具体化: remote userの固定相対root `.local/state/llm-manager/remote-helper`配下へ、request ID/request hashから操作directoryを導出する。既存itemをhash付き固定名で先に0600転送し、canonical requestを最後に公開してからrequest ID/hashだけで限定helperを起動し、固定`result.json`を1 MiB上限で取得する。期限・改ざん・item hash・cancelをhelper起動前にも検査する。system `ssh`/`scp`の固定argv、OpenSSH alias/ControlPath、0600 local一時file、bounded downloadを実装し、root helper起動はpasswordless/外部端末sudo専用invokerへ分離した。fake subprocessまでの検証で、実SSH転送Gateは未実施である。

Remote sudo invoker実装: system OpenSSHで固定`sudo -n -v`だけをpasswordless probeし、成功時は限定helperを非対話実行する。probe失敗時は外部端末の`ssh -t`内でsudo認証を行い、user stagingの固定result completionをbounded pollする。helper自身の失敗を認証失敗と誤認して再端末起動せず、cancel/timeout/terminal failureを分離する。fake runner/terminalのみで、実remote sudo認証Gateは未実施である。

Remote retention backend実装: immutable receipt hashへ束縛したcanonical retention recordを0600で保存し、hostごと30日かつ直近10世代の未保護copyを古い順に削除する。protected copyと最後の1 copyは自動削除せず、record改ざん、owner/mode、symlink、未知entryがあれば削除前にfail-closedにする。実remote helperのretention operationとproduction配置Gateは未実施である。

Dual-copy削除後照合core実装: local/remoteを独立にread-only観測し、`both_available`、`local_only`、`remote_only`、`both_deleted`、`unknown`の表示用状態へ集約する。片側だけ残った場合と観測不能・改ざんはattention requiredとし、自動的に残存copyを追加削除・再作成しない。実際のlocal/remote協調削除commandと再試行UXは未実装である。

特権helper protocol先行実装: protocol v1のcanonical JSON、request hash、10分以下の期限、operation/plan/host/change-set束縛を追加した。operationは`atomic_replace`, `remove_created_file`, `restore_file`, `daemon_reload`, `restart_unit`の固定enumのみで、ファイル対象はLLM-Manager専用Ollama drop-in、unitは`ollama.service`だけを許可する。shell、argv、環境変数、任意pathをschemaとして受け取らず、未知field、改ざん、期限切れ、未来時刻、path/unit逸脱を拒否する。drop-in書込metadataは0644/root:rootに固定し、removeにもbefore hashを必須とする。PolicyKit policy、root-owned helper executableと実systemd backendは残作業である。

Helper staging実装: staging pathはrequest入力にせず`operation_id/item operation_id`から固定導出する。root/item directory 0700、content 0600、owner、regular file、symlink、16 MiB上限、request/staged hashをstage時とhelper側verify時に再検証する。既存itemの上書き、world-readable file、world-writable root、内容差替え、予期しないcleanup entryを拒否する。root-owned helper executable、PolicyKit policyと実systemd操作は残作業である。

Helper execution core実装: 実行直前にrequest期限/hash、対象before hash、staged content hashを再検証し、固定operationを宣言順にbackendへ渡す。stale targetは変更前に拒否し、write/reload等の失敗後は後続operationを`not_executed`として停止する。backendはprotocolで分離し、単体テストではsandbox fakeだけを使用している。

Local system helper backend実装: 論理targetを専用Ollama drop-inと完全一致させ、regular file/symlink/16 MiB/親directory安全性を再検査する。書込は0644/root:root、atomic rename、file/parent fsyncを行い、service操作は`/usr/bin/systemctl daemon-reload`と`/usr/bin/systemctl restart ollama.service`の固定argvだけを生成する。明示sandbox mode以外の代替rootを拒否し、単体テストでは一時rootとfake runnerだけを使用している。packaged executableとPolicyKit actionの配置は残作業である。

Helper CLI/PolicyKit定義実装: CLI引数はoperation IDとrequest hashだけに限定し、`PKEXEC_UID`または`SUDO_UID`からuser runtime staging pathを固定導出する。root実行、requestの0600/owner/regular file/1 MiB上限、operation identityを再検査し、結果はstable codeだけのcanonical JSONで返す。PolicyKit actionはactive sessionの`auth_admin`、固定`/usr/bin/llm-manager-helper`に限定した。実debへのroot-owned配置とPolicyKit実desktop認証は残作業である。

Helper replay receipt実装: root-only receipt directoryへoperation IDを`O_EXCL`で実行前にclaimし、同一requestの再実行を`replayed_request`、異なるrequest hashによるID再利用を`operation_id_collision`として拒否する。receiptは0600、directoryは0700で、`executing`から`completed`または`failed`へterminal resultをatomic保存する。sandbox testでは成功・失敗・改ざん・CLI二重実行を再現している。

Local PolicyKit invoker実装: requestに必要な全contentをhash検証付きでstageした後、canonical requestを最後にimmutable stageし、`/usr/bin/pkexec /usr/bin/llm-manager-helper <operation-id> <request-hash>`の固定argvだけをrunnerへ渡す。helper結果は1 MiB以下のcanonical JSON、operation ID/kind/order/exit status一致を検証する。timeout、PolicyKit deny/dismiss、launch failure、helper failureをstable error codeへ分離した。単体テストはfake runnerのみで、実認証は起動していない。

Approved privileged apply境界実装: `ApprovalRecord.is_valid_for`へplan期限も追加し、plan/report/change-set/backup-policy/plaintext acknowledgement/plan期限/approval期限の一致をhelper request生成前に再検証する。MVPの単一Ollama専用drop-in root changeだけを`atomic_replace → daemon_reload → restart ollama.service`へ変換し、request期限をplan・approval・5分の最短値に束縛する。allowlist外path、非root/mixed/複数change、欠落restart/reloadをPolicyKit呼出し前に拒否する。

Privileged Safe Apply workflow実装: local root変更専用CoordinatorでBackup検証後だけhelper Applyを開始し、成功後にruntime validation、失敗時に別の期限付きhelper rollback requestを実行する。既存fileは`restore_file`、新規fileは`remove_created_file`を逆順生成し、その後`daemon_reload → restart ollama.service`を行う。write/reload/restart/runtime validationとrollback各段階のsandbox故障注入、`RECOVERY_REQUIRED`終端を追加した。manifestのchange-set hashと、approval/backup/manifest/request identityをhelper request・receipt対応hash・journalへ束縛した。実PolicyKit認証とsystemd操作は行っていない。

Local privileged境界統合test実装: root CoordinatorからLocalPolicyKitInvokerの固定argv、user staging、helper CLI、root-only replay receipt、DeclaredHelperExecutor、sandbox LocalSystemHelperBackendまでを一時directoryとfake service runnerで接続した。commit、runtime validation起因rollback、daemon-reload失敗起因rollbackについて、apply/rollbackが別receiptを持ちjournalのrequest hashと一致することを検証した。pkexec、実systemd、実設定は起動・変更していない。

Local deb先行Gate実装: Debian debhelper/dh-python構成、PolicyKit policy、manpage、root-owned固定helper wrapperを追加した。helper wrapperは`python3 -I`で起動し、pip console scriptによる特権導入を禁止する。binary debを一時copyでbuildし、artifact内のroot ownership、0755/0644 mode、isolated shebang、PolicyKit固定path、runtime dependencyを`verify-deb.sh`で検証した。実install/upgrade/remove/purgeとdesktop PolicyKit認証は未実施である。

Helper compatibility診断・Plan Gate実装: local/remoteそれぞれのhelperとroot-owned canonical metadataの固定pathをread-onlyで調べ、root:root ownership、0755/0644 mode、非symlink、content hash、package名、package version、protocol versionを全て満たす場合だけ特権境界へ進める。remote probeはsystem OpenSSHの固定`stat`/bounded `cat`へ接続し、user staging開始前とroot helper起動直前に再検証する。missing、unsafe、invalid、incompatible、probe例外はfail-closedにし、不一致時はstaging commandを発行しない。fake runnerまで完了し、実SSH互換診断Gateは未実施である。

Apply時helper再検証実装: 診断・Plan後のhelper差替えや削除を信用せず、root workflowはBackup前とhelper起動直前に互換性を再検証する。Backup前の失敗は永続物を作らず、検証済みBackup後の失敗はBackupを保持して未変更で停止する。いずれもinvoker、pkexec、systemd操作へ到達しないことをsandbox fakeで確認した。

暗号化基盤の実装: `cryptography` AES-256-GCMによるversioned canonical envelope、item 16 MiB上限、12-byte random nonce、backup ID/host fingerprint/targetを束縛するAAD、key reference/scope検査、改ざん・scope取り違え検出を追加した。生鍵はenvelopeへ保存せず`BackupKeyProvider`から取得する。LocalBackupStoreのcreate/verify/reload/restoreへ統合し、暗号policy hashをPlan/Approvalへ束縛した。鍵provider不在時は平文fallbackせず停止する。SecretStorage adapterはdefault collection、属性検索、OS unlock prompt、32-byte master keyのcreate/reuse、競合時再読込、cancel/timeout/unavailable停止を実装した。現在の開発環境にはSecretStorage依存が未導入のため、実desktop keyring Gateは引き続き残作業である。

Backup設定実装: 一般配布buildは暗号化ON、明示的development buildはOFFを初回既定とし、保存済みユーザー選択が存在すればbuild既定で上書きしない。設定は0600、親directoryは0700、canonical schemaで保存する。暗号化OFFのApplyは`ApprovalRecord.plaintext_backup_acknowledged=true`がなければ拒否する。

## Phase 5: PySide6 GUI

- Hosts/Diagnose/Recommendations/Review/Results/Backup
- QThreadPool coordinator、progress、cancel、host lock
- accessibility、error UX、stale approval
- locale自動選択、言語切替、日本語/英語catalog、fallback/layout test

成果物: 6工程の画面、worker coordinator、状態遷移、GUI acceptance tests。

Exit: acceptance scenariosがGUI経由で完了し、UI threadがblockしない。対応要件: FR-APPROVEと全表示要件、AC-05、AC-09。

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
