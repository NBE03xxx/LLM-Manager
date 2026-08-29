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

残作業: Secret Service実desktop Gate、remote復旧copy、PolicyKit/remote helperとdaemon-reload/restart実行、実環境integration Gate、remote journalとのSSH切断統合。これらが完了するまでPhase 4 Exitは未達とする。

特権helper protocol先行実装: protocol v1のcanonical JSON、request hash、10分以下の期限、operation/plan/host/change-set束縛を追加した。operationは`atomic_replace`, `remove_created_file`, `restore_file`, `daemon_reload`, `restart_unit`の固定enumのみで、ファイル対象はLLM-Manager専用Ollama drop-in、unitは`ollama.service`だけを許可する。shell、argv、環境変数、任意pathをschemaとして受け取らず、未知field、改ざん、期限切れ、未来時刻、path/unit逸脱を拒否する。drop-in書込metadataは0644/root:rootに固定し、removeにもbefore hashを必須とする。PolicyKit policy、root-owned helper executableと実systemd backendは残作業である。

Helper staging実装: staging pathはrequest入力にせず`operation_id/item operation_id`から固定導出する。root/item directory 0700、content 0600、owner、regular file、symlink、16 MiB上限、request/staged hashをstage時とhelper側verify時に再検証する。既存itemの上書き、world-readable file、world-writable root、内容差替え、予期しないcleanup entryを拒否する。root-owned helper executable、PolicyKit policyと実systemd操作は残作業である。

Helper execution core実装: 実行直前にrequest期限/hash、対象before hash、staged content hashを再検証し、固定operationを宣言順にbackendへ渡す。stale targetは変更前に拒否し、write/reload等の失敗後は後続operationを`not_executed`として停止する。backendはprotocolで分離し、単体テストではsandbox fakeだけを使用している。

Local system helper backend実装: 論理targetを専用Ollama drop-inと完全一致させ、regular file/symlink/16 MiB/親directory安全性を再検査する。書込は0644/root:root、atomic rename、file/parent fsyncを行い、service操作は`/usr/bin/systemctl daemon-reload`と`/usr/bin/systemctl restart ollama.service`の固定argvだけを生成する。明示sandbox mode以外の代替rootを拒否し、単体テストでは一時rootとfake runnerだけを使用している。packaged executableとPolicyKit actionの配置は残作業である。

Helper CLI/PolicyKit定義実装: CLI引数はoperation IDとrequest hashだけに限定し、`PKEXEC_UID`または`SUDO_UID`からuser runtime staging pathを固定導出する。root実行、requestの0600/owner/regular file/1 MiB上限、operation identityを再検査し、結果はstable codeだけのcanonical JSONで返す。PolicyKit actionはactive sessionの`auth_admin`、固定`/usr/bin/llm-manager-helper`に限定した。実debへのroot-owned配置、PolicyKit実desktop認証、replay receiptは残作業である。

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
