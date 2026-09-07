# Phase 0 Traceability Matrix

Phase 4追跡注記: backup evidence retention executionのcanonical自己hash、request/host/deletion/reconciliation binding、immutable 0700/0600保存、改ざん・filename・metadata拒否を`BackupEvidenceRetentionPlannerTests`で検証済み。executorの`completed`/`partial`/`failed`全終了経路を保存へ接続し、保存失敗と途中削除後の保存失敗ではstable persistence errorから生成済みexecutionを取得できることを故障注入で検証する。再起動後のhost/fingerprint単位strict一覧、未知entry、fingerprint変更、同一request重複の拒否も同test classで検証する。

`BackupEvidenceRetentionCleanupServiceTests`は、再起動後strict executionに束縛した明示的cleanup requestだけをdispatchし、requestをmutation前に0700/0600 immutable storeへ保存することを検証する。改ざん、期限切れ、binding変更、`completed`、cancel、cleanup ID衝突、保存済みrequest改ざんをcleanup Port呼出し前に拒否する。cleanup executorの残存suffix再照合、成功、cancel、途中失敗の停止とimmutable execution保存も検証し、orphan自動判定・自動削除は行わない。

`BackupInventoryServiceTests`はlatest evidence retention executionと残存kindを再起動後repositoryから表示し、未完了executionをattentionへ反映する一方、dual-delete/retry mutation authorityへ使用せずread-only refreshだけを提示することを検証する。

`BackupEvidenceRetentionRuntimeTests`はexecution/request storeをabsolute XDG stateまたはhome fallbackの固定subdirectoryへ配置し、0700 application/runtime root、相対XDG、root path、symlink、unsafe modeをsandboxで検証する。

実OpenSSH negative transport Gateでは`development`とAI serverにproduction adapterでread-only接続し、remote helper未導入をfixed helper/metadata `stat`だけで判定した。positive transport Gateではdisposable `llm-manager-gate`へ事前導入済みdebを使い、compatibility再検証、user staging、外部端末sudo、root-owned AES-GCM recovery copy、canonical receipt再取得、staging cleanupまで成功した。`RemoteHelperRecoveryCopyStoreTests`と`RemoteRecoveryRuntimeTests`は、request identityのmutation前immutable保存、XDG固定配置、再起動後の同一receipt回収、manifest/fingerprint binding、改ざん、衝突、未知entry、owner/mode/symlink拒否を検証する。さらに実2プロセスGateで、helper実行側終了後に新プロセスがhelperを再実行せず同一hash receiptを回収・検証・cleanupできることを確認した。

`OpenSshRemoteSudoInvokerTests`、`OpenSshRemoteRetentionTests`、`OpenSshRemoteDeletionTests`は外部端末sudoで許可する3つの固定operation、retention/deletion取り違え拒否、passwordless互換を検証する。実remote retention Gateは削除0、残存3、`completed` result永続化、cleanup完了を確認した。

`RemoteHelperRecoveryCopyStoreTests`はlocal immutable receipt保存、staging消失後の再起動load、manifest binding、canonical改ざん、unsafe metadataを検証する。`RemoteRecoveryRuntimeTests`はreceipt rootをattempt rootと分離した固定XDG配置へ束縛する。

実remote deletion Gateは専用copyに対し、永続receiptからのrequest生成、root receipt/envelope/key/path/item再検証、`deleted` canonical result、staging cleanup、local正本保持、別retention requestによる対象不在を確認した。既存3件は変更していない。

実remote deb lifecycle Gateはdisposable Ubuntu 26.04で同一版reinstall、remove、purge、再installを行い、最新private runtime hash、root ownership/mode、package不在時の`missing` fail closed、再install後の`ready`、dpkg管理外backup/key保持を確認した。local debもdisposable Ubuntu 26.04 desktopでinstall/reinstall/remove/purge相当/reinstall/upgrade、root ownership/mode/action登録を確認した。Ubuntu 26.04のPolicyKit package分割に合わせdependencyを`polkitd`+`pkexec`へ修正し、実pkexecで継承`SUDO_UID`と競合しない`PKEXEC_UID`専用local identity境界を確認した。Debian 13ではstock runtimeに合わせた依存下限、両deb lifecycle、PolicyKit success/明示deny、Gate専用systemd操作とcleanupを確認した。Liveのpasswordless/admin sessionでは無対話許可となったdismissも、通常installしたpassword-backed GNOME sessionで認証dialogのCancel、exit 126、unit/marker無変更を確認した。

実SSH転送切断Gateはdisposable Ubuntu 26.04への16 MiB user staging転送を帯域制限し、専用ControlMasterだけを転送中に終了した。production `RemoteHelperRecoveryCopyStore` → `UserOnlySshRecoveryTransport` → `OpenSshUserStagingRunner`は`remote_staging_failed`で停止し、request-lastの`request.json`と`result.json`を公開せず、root helperを一度も起動しなかった。local正本の再検証成功と、許可されたuser staging cleanup後のoperation directory不在を確認した。

実remote journal Gateは特定operation/request hashだけの一時NOPASSWD read ruleを使い、production compatibility Gateと`OpenSshRemoteJournalPort`からroot:root 0700/0600のcanonical evidence 928 bytesを取得した。local journal/manifest/host/fingerprint/target bindingを検証してremote targetを`unapplied`へ照合し、Apply/rollbackを起動しなかった。Gate後はroot evidenceとruleを削除し、同じtransportが`remote_journal_failed`へfail closedすること、通常の`sudo -n`も拒否されることを確認した。

| Requirement | Design artifact | Planned verification | Gate |
|---|---|---|---|
| FR-HOST-01 | architecture, ADR-0001, gui | `OpenSshHostAdapterTests`, `OpenSshConfigAliasesTests`, `DiagnosticTaskFactoryTests`, `OpenSshHostIdentityResolverTests`, `BrokerTests`（Local先頭、literal alias、Include、system OpenSSH composition、effective destination、strict known-host一致、LF/CRLF fingerprint、認証未完了判別、alias ControlMaster、socket reuse/終了、変更/timeout fail closed）。実config候補、`development` timeout negative、`llm-manager-gate` ControlMaster read-only complete/cleanup positive Gate | Phase 5一部完了 |
| FR-DIAG-01..03 | diagnostics, version matrix | `LinuxParserTests`, `LinuxProbeTests`, partial report完了、実環境待ち | Phase 2一部完了 |
| FR-OLLAMA-01 | version matrix, allowlist | `OllamaAdapterTests` fixture完了、0.33.2実環境待ち | Phase 2/3 |
| FR-OPENCODE-01 | version matrix, allowlist | `OpenCodeAdapterTests` JSONC fixture完了、1.18.25探索統合待ち | Phase 2/3 |
| FR-PROFILE-01 | optimization, rule fixtures, gui | `ProfileGoldenTests`, `RecommendationPresentationTests`, `QtRuntimeTests`（3 profile定義、Agent切替、日本語再描画） | Phase 3 core完了/Phase 5表示完了 |
| FR-REC-01..02 | optimization, ADR-0002, gui | `RuleEngineTests`, `ConflictTests`, `RecommendationPresentationTests`, `QtRuntimeTests`（現在/推奨値、severity、actionable、理由、影響、秘密値redaction、実Qt一覧） | Phase 3 core完了/Phase 5表示完了 |
| FR-PLAN-01..02 | allowlist, safe-apply, gui | `OpenCodePlannerTests`, `OllamaDropInPlannerTests`（root helper capability Gateを含む）、`RecommendationPresentationTests`/`QtRuntimeTests`（actionable選択、selected ID binding、QThreadPool生成、masked diff/root/restart Review）、`BuildSelectedOpenCodeChangePlanTests`/`DiagnosticTaskFactoryTests`（report/expiry/host identity再検証、bounded再読込、before hash、strict SSH/ControlMaster cleanup、stale/encoding fail closed）。Ubuntu 26.04/PySide6 6.10.2関連25件Gate完了 | Phase 3 core完了/Phase 4 hardening/Phase 5 planning表示完了 |
| FR-PLAN-01..02 (local root) | allowlist, safe-apply, gui | `BuildSelectedOllamaChangePlanTests`（plan/report/selection/host identity、helper再probe、固定drop-in bounded read、before hash、missing/symlink fail closed）、`DiagnosticTaskFactoryTests`（production local helper capability、local-only注入、Ollama/OpenCode分岐、混在/SSH root I/O前拒否） | Phase 6 diagnosis/planning composition完了 |
| FR-APPROVE-01 | data-model, safe-apply, gui | `ApprovalTests`, `CreateApprovalRecordTests`, `CoordinatorTests`（plan/report/change/backup policy hash・actor・平文ack・最短期限・apply統合）、`GuiPresenterTests`/`QtRuntimeTests`（明示checkbox、取消、timer/再検査によるstale失効、内容変更時破棄、独立したApply準備、ResultsへのApproval ID引渡し）。Ubuntu 26.04/PySide6 6.10.2関連24件Gate完了。実Applyは後続 | Phase 4 core完了/Phase 5 Apply前承認完了 |
| AC-06 | safe-apply, gui | `ProductionApplyAvailabilityTests`（4経路分類、binding、mixed privilege拒否、明示完成routeだけ有効）、`QtProductionCompositionTests`（entrypointはlocal userだけ公開）、`QtRuntimeTests`（factoryなし/未完成routeは実行不能、local root無効→local user有効、実local compositionのencrypted backup/Apply/audit/journalから`committed`、validation故障時`rolled_back`、restore故障時`recovery_required`表示）、`LocalUserApplyTaskFactoryTests`（root限定、unsafe state/symlink拒否）、`LocalUserApplySecretServiceGateTests`（Ubuntu desktop実Secret Service key作成・暗号化Apply・削除） | Phase 5 local user production接続/GUI success・failure path完了、他3 route fail closed |
| AC-06 (local root) | safe-apply, gui | `LocalRootApplyTaskFactoryTests`（local/root-only、private state、helper二重readiness、journal/audit、user/root router、mixed privilege拒否）、`PrivilegedSafeApplyCoordinatorTests`、`PrivilegedBoundaryIntegrationTests` | Phase 6 production composition完了、GUI Gate前のためfail closed |
| FR-BACKUP-01 | ADR-0005, threat model | backup/crypto/dual-copy/remote recovery/retention/deletion/inventory/evidence retention test群でintegrity、binding、30日/10世代、明示cleanup、fault injectionを検証。実SSH positive recovery/retention/deletion/転送切断とDebian 13 stock crypto/Secret Service/package runtime Gate完了 | Phase 4 core完了 |
| FR-APPLY-01 | ADR-0004, allowlist | atomic/coordinator/helper/PolicyKit/privileged integration/packaging/remote sudo test群でpath、binding、固定operation、fault injectionを検証。Ubuntu 26.04とDebian 13でPolicyKit success/dismiss/deny、package lifecycle、Gate専用systemd操作完了。実Ollama/OpenCode targetは意図的に未変更 | Phase 4 core完了 |
| FR-VALIDATE-01 | allowlist, version matrix | `FileValidatorTests`, `ProductRuntimeValidatorTests`, `OllamaAdapterTests`, `OpenCodeAdapterTests`, `CoordinatorTests`（file hash/JSONC/systemd drop-in構文、service/API/effective environment、再読込、失敗時rollback）。特権/systemd integrationはGate専用unitで完了 | Phase 4 core完了（製品target実Applyは未実施） |
| FR-ROLLBACK-01 | ADR-0005, threat model | coordinator/privileged/journal test群で逆順restore、故障時`RECOVERY_REQUIRED`、SSH切断後のbindingとread-only照合を検証。実remote helper/SSH root evidence取得と`unapplied`照合完了 | Phase 4 core完了（製品target実rollbackは未実施） |
| FR-AUDIT-01 | threat model | `LocalAuditLogTests`, `CoordinatorTests`, `LocalOperationJournalTests`（redaction、hash-chain永続化、tamper/deletion/replay/state reconciliation） | Phase 4 core完了 |
| FR-I18N-01..02 | ADR-0006, gui | `UiI18nTests`, `RecommendationPresentationTests`, `QtRuntimeTests`（ja/en locale選択、英語fallback、catalog key完全性、button/status/profile/recommendation即時更新、6工程scroll、主要summary折返し）。実display accessibilityはPhase 6 acceptance | Phase 6合成layout Gate完了、実display待ち |
| AC-09/10 | ADR-0003, architecture | `ArchitectureTests`（coreからUIへの逆依存なし）、`GuiPresenterTests`（二重開始/cancel/state transition、ChangeSet生成、承認失効、Apply outcome）、`QtWorkerBoundaryTests`、`QtWindowBoundaryTests`、`QtRuntimeTests`。Ubuntu 26.04/PySide6で別thread、event-loop sentinel、長時間継続worker中の20回以上のevent処理と協力的cancel、close時cancelとworker終了待機、Diagnose→Recommendations→Review→Approval→local user production Applyのsuccess/rollback/recovery Results vertical slice完了。未完成mutation routeはI/O前にfail closed | Phase 6 close/layout/長時間合成Gate完了、実production負荷待ち |
| MVP GUI deb | packaging, gui | `DebianPackagingTests`、`packaging/verify-deb.sh`（isolated non-root GUI launcher、desktop entry、icon、PySide6依存、root ownership/mode、PolicyKitはhelper限定）、binary deb build/archive Gate。Ubuntu 26.04でAPT install、UID 1000 Wayland日本語GUI、同版reinstall、purge、snapshot復元完了。Debian 13でstock Python 3.13.5/PySide6 6.8.2.1依存解決、UID 1000 offscreen起動、reinstall、purge、package集合復元完了。Debian実display/menu起動待ち | Phase 6 lifecycleほぼ完了、Debian display待ち |
| FR-BACKUP-01 (GUI) | backup inventory, gui | `QtRuntimeTests.test_backup_inventory_refresh_is_read_only_and_localized`（初期I/Oなし、明示refresh、状態/presence/protection/attention/action名表示、英日再描画で再読込なし）、`LocalApplyInventoryTests`（strict restart manifest/journal結合、tamper/未知entry拒否、空state非生成、SSH分離）、`QtProductionCompositionTests`（local production factory接続）、`QtWindowBoundaryTests`（accessible controls、UI層にprocess/network/privilege importなし）。mutation controlは未接続。SSH loaderは現行固定journal readがID列挙不能、retention listがroot prune内部backendであるため、権限境界を拡張せずfail closedを維持 | Phase 5 local read-only inventory完了、SSH protocolは独立判断待ち |
| FR-BACKUP-02 (restore preview) | backup inventory, gui, safe-apply | `RestorePreviewTests`（strict manifest由来のmetadata-only canonical preview、content非露出、明示review、host/backup/manifest/preview hash、actor、最短expiry binding、tamper/別backup/期限切れ拒否）、`QtRuntimeTests`（worker表示、exact checkbox承認、refresh/selection/host/timer失効、本文非表示） | Phase 5 local user production接続完了 |
| FR-BACKUP-03 (restore preflight) | safe-apply, backup inventory | `RestorePreflightTests`（実行直前strict manifest再読込、canonical preview/approval/host/backup/manifest/target metadata/allowlist binding、短命hash authorization、tamper・変更・mismatch・cancel拒否）、`LocalUserRestoreTaskFactoryTests`（authorizationを単一worker内部に限定） | Phase 5 local user production接続完了 |
| FR-BACKUP-04 (local restore executor) | safe-apply, backup inventory | `LocalRestoreExecutorTests`（単一target限定、authorization/expiry/strict manifest/current targetの復号前後再検証、atomic replace、変更・複数target拒否時の無変更）、`LocalUserRestoreSecretServiceGateTests`（Ubuntu desktop実Secret Service暗号化restore/key cleanup） | Phase 5 local user production接続完了、root/SSH未接続 |
| FR-BACKUP-05 (restore evidence) | safe-apply, audit, gui | `RestoreExecutionTests`（mutation前immutable attempt、authorization一回消費、開始/完了audit、immutable result、restart/tamper/replay/fault injection、COMMITTED/FAILED/UNKNOWN）、`LocalUserRestoreTaskFactoryTests`（FAILED strict再読込）、`QtRuntimeTests.test_restore_result_renders_only_explicit_evidence_state`（state/error/persisted表示、不正result拒否） | Phase 5 local user production接続完了、自動retryなし |
| FR-BACKUP-06 (restore restart inventory) | backup inventory, gui | `RestoreExecutionTests`（strict全entry、unknown/orphan/binding拒否、attempt-only保持）、`LocalApplyInventoryTests`（backup ID結合、attention、自動retryなし）、`QtRuntimeTests.test_restore_completion_requires_explicit_refresh_to_load_execution_inventory`（実restore後の明示refreshでCOMMITTED/attention false、approval再利用不可）。Ubuntu 26.04/PySide6 6.10.2 end-to-end Gate完了 | Phase 5 local user production接続完了、SSH inventory protocol待ち |
| FR-BACKUP-07 (production restore routes) | backup inventory, safe-apply, gui | `ProductionRestoreAvailabilityTests`（4経路の固定理由、明示完成routeのみ許可）、`QtProductionCompositionTests`（local userのみ公開）、`QtRuntimeTests.test_ssh_backup_restore_route_is_disabled_before_inventory_io`（SSHは固定理由、button無効、I/Oなし） | Phase 5 local user完了、local root/SSHはprotocol完成までfail closed |
| AC-13/14 | allowlist, ADR-0004/0005 | unknown version denial、`LocalOperationJournalTests`（before/after/unknown）、remote統合待ち | Phase 4一部完了 |
| SSH helper prerequisite | ADR-0008, version matrix | `HelperCompatibilityProbeTests`, `OpenSshHostAdapterTests`, `OpenSshUserStagingRunnerTests`, `DiagnoseHostTests`, `OllamaDropInPlannerTests`（local/remote fixed path、absent、symlink、root owner/mode、content hash、canonical package/version/protocol metadata、system OpenSSH固定stat/cat、staging前・invoke直前再検証、fail-closed capability/Plan Gate）、実SSH positive compatibility/user staging/external-terminal sudo/recovery receipt Gate完了 | Phase 4一部完了 |
| Backup crypto/recovery | ADR-0009, threat model | `BackupCryptoTests`, `SecretServiceKeyProviderTests`, `SecretStorageBackendTests`, `RemoteRootKeyProviderTests`, `BackupSettingsTests`, `LocalBackupStoreTests`, `DualCopyPrivilegedBackupStoreTests`, `CoordinatorTests`（AES-GCM/AAD/nonce/tamper/key scope/size、local Secret Service key create-reuse、binding欠落時stable unavailable、remote root key O_EXCL create-reuse/0700/0600/owner/symlink/size/root/path、remote recovery production固定path/root/ownerとsandbox統合、cancel/build default/user persistence/plaintext acknowledgement/restore/approval invalidation）、Ubuntu 26.04とDebian 13 desktopでdefault collectionへのGate専用key create/reload/delete完了 | Phase 4一部完了 |
| Endpoint confinement | ADR-0010, setting allowlist | loopback allow、external/redirect/userinfo deny | Phase 3/4 |
| OpenCode safe edit | ADR-0011, setting allowlist | scalar span、comment、escape、byte-diff fixtures | Phase 3/4 |

Release checklistでは各行を具体的なtest IDへ置換する。設計artifactだけで受け入れ条件を完了扱いにしない。

Phase 6 security/privacy code review: 引用符付きsecretの全体redactionと永続log非露出、`ProcessRunnerTests`のstream別受信中上限/回収/timeout/cancel、`ApplyOutcomeTests`の表示前redaction/4 KiB上限、`LocalSystemHelperBackendTests.test_production_service_runner_discards_unused_output`を検証した。SEC-02 focused 13 testはUbuntu 26.04/Python 3.14.4とDebian 13/Python 3.13.5でも成功。範囲と残存trust boundaryは[review記録](validation/phase6-security-privacy-review-2026-09-05.md)を参照する。

Phase 6利用者向け復旧文書: [Backup・Rollback・Recoveryガイド](recovery-guide.md)にproduction route matrix、Apply結果、local user手動restore、`recovery_required`/`unknown`時の停止・identity/hash照合、local/remote鍵喪失、保持、upgrade/uninstall、fail-closed routeを記載した。MVP scope項目7の文書成果物とする。

Phase 6 SBOM/license/signing: `DebianPackagingTests.test_direct_dependency_sboms_are_cyclonedx_and_match_packages`、local/remote artifact verifierでCycloneDX 1.6直接依存SBOM、MIT copyright、third-party noticesの収録を検証する。[MVP Release Checklist](release-checklist.md)でresolved-environment SBOM、Qt package copyright、artifact checksum/OpenPGP署名、signed tag、公開後再検証をrelease blockerとして追跡する。

Phase 6 Qt hardening: `QtRuntimeTests.test_all_pages_scroll_and_long_summary_labels_wrap`、`test_close_requests_cancel_and_waits_for_worker_completion`、`test_long_running_task_keeps_processing_events_and_cancels_promptly`と`QtWindowBoundaryTests.test_pages_are_scrollable_and_close_waits_for_workers`でlayout、終了処理、長時間継続workerのevent処理を検証した。Ubuntu 26.04の実PySide6で23件（1 expected skip）が成功した。実display accessibilityと実production backend負荷は未完了。[検証記録](validation/phase6-qt-hardening-2026-09-05.md)を参照する。

Phase 6 production diagnosis performance: Ubuntu 26.04で実production local read-only診断をQt workerから実行し、`partial`終端、25.234 ms、最大event gap 10.383 ms、最大RSS 67,352 KiB、worker cleanupを確認した。単一sampleかつruntime/client不在のためAC-09の補助evidenceとし、最終性能判定にはcomplete/SSH/Apply系の複数sampleを要求する。[検証記録](validation/phase6-production-diagnosis-performance-2026-09-05.md)を参照する。

Phase 6 accessibility follow-up: primary control、status、summaryのaccessible nameをvisibleな英日文言と同期し、言語切替runtime assertionを追加した。host全527 testとUbuntu 26.04実PySide6 24件（1 expected skip）が成功した。実screen reader Gateは未完了。

Phase 6 cancel非協力区間の終了待機UX: `QtRuntimeTests.test_close_explains_wait_for_task_that_does_not_poll_cancel_promptly`で、300 ms tokenを確認しない有限taskにcloseを要求し、英日catalog完全性、日本語の明示的な安全停止待機、accessible name同期、重複cancel無効、10回以上のevent処理、worker終端後だけcloseを検証した。Ubuntu 26.04実PySide6で関連31件（1 expected skip）が成功。永久に戻らないin-process taskは強制終了しない。[検証記録](validation/phase6-close-wait-ux-2026-09-05.md)を参照する。

Phase 6 local user Apply performance: production `LocalUserApplyTaskFactory`のAES-GCM backup、atomic Apply、validation、audit、journal、rollbackをhost/Ubuntu 26.04/Debian 13の一時rootで各15 sample実行した。全45 sampleで`committed`/`rolled_back`/`recovery_required`、期待target state、backup/journal/audit/private stateを確認。Debianの一時依存3件は明示purge後、導入前2236 packageとadded/missing空で一致。[検証記録](validation/phase6-local-user-apply-performance-2026-09-05.md)を参照する。

Phase 6 complete local diagnosis: 固定system PATH外の標準user OpenCode binaryを、owner/mode/file/symlinkと固定parent境界の検査後だけabsolute allowlistへ加え、production診断とlocal user Apply validatorへ接続した。安全file採用とwritable/symlink拒否をunit testで検証。実Ollama 0.33.2/OpenCode 1.18.25のread-only production診断5 sampleは全`complete`、434.000–509.774 ms。[検証記録](validation/phase6-complete-local-diagnosis-performance-2026-09-05.md)を参照する。

Keyboard follow-up: Hosts画面でhost selectorからlanguage selectorへTab移動するruntime assertionを追加した。host全528 test完走。追加分の実PySide6確認と実screen reader Gateは未完了。

Phase 6 remote helper SBOM: Ubuntu 26.04の一時snapshot内で修正後dev debを導入し、通常userで1908 packageの環境SBOMを採取した。CycloneDX 1.6、1938 evidence checksum、109 installed payload fileのdeb照合に成功。snapshot復元後のpackage版/manual一覧一致とartifact不在を確認し停止済み。最終release検証とは区別する。[検証記録](validation/phase6-remote-sbom-2026-09-05.md)。

Phase 6 root planning保全: Ollama専用drop-inの部分変更で未選択設定が失われる不具合を修正。literal assignment・コメント・改行を保持し、未対応構文と重複keyは計画生成を拒否する。planner/applicationの新規7 testと全544 test（23 skip）が成功。root route公開とscope変更は行っていない。[検証記録](validation/phase6-root-drop-in-preservation-2026-09-05.md)。

Phase 6 local root restore契約: [専用intent protocol](local-root-restore-protocol.md)とcodecを追加。固定target、UID/host、backup/current state、review binding、有効期間を検証する。新規9 testと全553 test（23 skip）が成功。codecはauthorityを発行せず、privileged inventory/preflight/executor/resultは未接続。[検証記録](validation/phase6-local-root-restore-protocol-2026-09-05.md)。

Phase 6 local root restore preflight: 専用requestとtrusted review/backup/current/attemptのread-only照合を追加。新規10 testで偽要求、stale state、全7 read直後のcancel/期限、例外を検証。全563 test（23 skip）が成功。root store/復号/lock/executorは未接続で、戻り値はauthorityではない。[検証記録](validation/phase6-local-root-restore-preflight-2026-09-05.md)。

Phase 6 root backup evidence reader: origin recordと固定保存先を定義し、owner/group/mode/no-follow/hardlink/size/inode変更/ciphertext hashを検証するreaderを追加。実一時fileの新規12 testと全575 test（23 skip）が成功。producer/鍵/復号/preflight接続は未完了。[検証記録](validation/phase6-root-backup-evidence-reader-2026-09-05.md)。

Phase 6 root origin capture: 固定target採取、strict root key read、AES-GCM/AAD/復号照合、payload先行/record最後の排他公開を追加。新規14 testと全589 test（23 skip）が成功。中断保存/最終fsync失敗は成功扱いせず、既存IDを上書きしない。production未接続。[検証記録](validation/phase6-root-backup-capture-2026-09-05.md)。

Phase 6 root key/origin: 明示key provisioning・ready marker・strict key read、origin参照付きreview、実復号/再読込verifierを追加。provisioningからpreflightのsandbox統合と全600 test（23 skip）が成功。review/attemptの実storeとproduction接続は未完了。[検証記録](validation/phase6-root-key-origin-preflight-2026-09-05.md)。

Phase 6 root restore store: review/attempt/resultの不変保存とstrict read、期限/履歴分離、再実行拒否を追加。統合preflightは実storeを使用。新規14 testと全614 test（23 skip）が成功。対象lock/audit/executor/production認可は未接続。[検証記録](validation/phase6-root-restore-store-2026-09-05.md)。

Phase 6 root restore execution: target flock、永続attempt/start audit、最終照合/期限guard、単一復元とterminal evidenceを実装。実一時fileの新規14 testと全628 test（23 skip）が成功。実service/認可/privileged dispatch/他mutator排他/OS Gateは未完了。[検証記録](validation/phase6-root-restore-execution-2026-09-05.md)。

Phase 6 root restore service (2026-09-06): 固定source openerとsystemctl/curl validationを追加。effective env、service state、loopback/HTTP200/API schema、timeout/cancelを模擬commandで検証。新規11 testと全639 test（23 skip）が成功。実service/認可/privileged composition/OS Gateは未完了。[検証記録](validation/phase6-root-restore-service-2026-09-06.md)。


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


## Ubuntu Qt Gate追記（2026-09-06）

Ubuntu 26.04/Python 3.14.4/PySide6 6.10.2でoffscreen関連52 testを実行、51成功・1 expected skip。新規GUI 2件（履歴照会の重複抑止、照会中close/遅延結果破棄）も成功。詳細: `docs/validation/phase6-root-status-qt-ubuntu2604-2026-09-06.md`。package追加なし、host/guest検証物cleanup済み、両VM shut off確認。実PolicyKit/installed deb/実display/Debian Qt Gateは未完了。次もPhase 6: 専用実行認可/CLI・production audit・要求間排他・provisioning・最終Gate。root mutation非公開、全変更未コミット。


## Strict root restore audit（2026-09-06）

root復元専用audit adapterと固定openerを追加。root metadata/no-follow、hash chain/HEAD、request開始終了対応、排他、event先行/fsync/HEAD更新、中断証拠のfail closedを実装。新規9 test（実一時復元coordinator接続含む）、host全722 test（691成功・31 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-audit-2026-09-06.md`。専用実行認可/CLIのproduction composition、要求間排他、provisioning、実PolicyKit/installed deb/OS Gateは残件。root mutation非公開、実環境変更なし、全変更未コミット。現在・次ともPhase 6。


## Fixed root restore composition（2026-09-06）

root復元の固定production compositionとStoredRootRestorePreflightを追加。backup/key/source/store/audit/serviceを接続し、root guard・audit chain事前検査・全FDの例外時解放を実装。新規6 test（実store/復号/target/auditを使うport統合含む）、host全728 test（697成功・31 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-composition-2026-09-06.md`。compositionは認可ではなく、専用実行CLIは未公開。要求間排他・provisioning・PolicyKit/installed deb/OS Gateも残件。実環境変更なし、全変更未コミット。現在・次ともPhase 6。

## Dedicated root restore execution CLI（2026-09-06）

専用execute CLI/action、canonical request/identity/期限検査、terminal result binding、
unconfirmed/no-retry契約を`tests/test_root_restore_execute_cli.py`で追跡する。package収録は
`tests/test_distribution.py`と`packaging/verify-deb.sh`で検証する。詳細は
`docs/validation/phase6-root-restore-execute-cli-2026-09-06.md`。

## Root restore execution client（2026-09-06）

固定pkexec transport、terminal result validation、unconfirmed/no-retry、認証拒否境界を
`tests/test_root_restore_execute_client.py`で追跡する。詳細は
`docs/validation/phase6-root-restore-execute-client-2026-09-06.md`。

## Root restore final consent（2026-09-06）

保存receipt/live request binding、hash-bound consent、single dispatch、unconfirmed-only status、
close時の遅延結果破棄を`tests/test_root_restore_review_session.py`、
`tests/test_root_restore_execution_session.py`、`tests/test_root_restore_execution_dialog.py`
で追跡する。英日表示keyの一致は`tests/test_ui_i18n.py`で追跡する。詳細は
`docs/validation/phase6-root-restore-final-consent-2026-09-06.md`。Qt runtime 4件は
Ubuntu 26.04/Python 3.14.4/PySide6 6.10.2でも成功済み。
fresh dev debへの新規module・launcher/action/manpage/SBOM収録は
`packaging/verify-deb.sh`とarchive inspectionで追跡する。

## Root restore installed deny/provisioning Gate（2026-09-06）

installed file integrity/owner/modeは`dpkg -V`と`stat`、独立action/path/active policyは
`pkaction --verbose`、inactive denyは`pkexec --disable-internal-agent`で追跡する。
installed privileged entryのpre-I/O拒否と一時root keyの0600作成・安定読込・重複拒否は
QEMU guest agentのroot fixtureで追跡する。証拠とsnapshot cleanupは
`docs/validation/phase6-root-restore-installed-deny-provisioning-2026-09-06.md`に記録する。

## Root restore valid OS Gate（2026-09-06）

installed origin capture/key/review/request/execute、固定target postcondition、実systemd restart、
loopback API、immutable result、strict audit、status reconciliation、replay拒否を
`docs/validation/phase6-root-restore-valid-os-gate-2026-09-06.md`のUbuntu snapshot Gateで
追跡する。interactive PolicyKit promptはこのGateの対象外として明示的に未完了を維持する。

## Local-root restore publication review（2026-09-07）

production allowlistが`LOCAL_USER`のみであること、availability省略時の既定拒否、
`requires_root=True`によるlocal/SSH分離、workflow呼出し前のGate、専用PolicyKit
action/isolated launcher/package検証をコード横断で再照合した。active desktopの
prompt/cancel/auth evidenceが未取得のため`LOCAL_ROOT`は非公開継続と判定した。詳細は
`docs/validation/phase6-root-restore-publication-review-2026-09-07.md`。公開境界は
`tests/test_ui_qt_app.py`、`tests/test_ui_qt_runtime.py`、
`tests/test_ui_qt_window.py`、`tests/test_restore_availability.py`で追跡する。

## Recovery procedure acceptance review（2026-09-07）

利用者向け`docs/recovery-guide.md`をApply `recovery_required`、restore
`failed`/`unknown`、backup key喪失、片側copy/key喪失の実装状態機械と照合した。
mutation/cleanup停止、evidence保全、before/after hash照合、自動retry禁止、健全側の
copy/keyを同一IDで再生成しない境界を確認した。詳細は
`docs/validation/phase6-recovery-procedure-acceptance-2026-09-07.md`。

## Public route documentation audit（2026-09-07）

READMEとrecovery guideの現行route説明をproduction availabilityと照合し、local root
手動restoreをprotocol未完成ではなく「専用実装・disposable OS Gate済み、active
desktop PolicyKit公開Gate待ち」として明確化した。local root Applyのactionable rule待ち、
SSH root ApplyとSSH user/root restoreのprotocol待ちは区別して維持する。詳細は
`docs/validation/phase6-public-route-documentation-audit-2026-09-07.md`。
