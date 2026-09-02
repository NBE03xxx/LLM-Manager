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
| FR-HOST-01 | architecture, ADR-0001, gui | `OpenSshHostAdapterTests`, `OpenSshConfigAliasesTests`, `DiagnosticTaskFactoryTests`, `OpenSshHostIdentityResolverTests`（Local先頭、literal alias、Include、system OpenSSH composition、effective destination、strict known_hosts、negotiated fingerprint、変更/timeout fail closed）。実config候補2件、`development` timeout negative Gate | Phase 5一部完了（対話ControlMaster/positive Gateは後続） |
| FR-DIAG-01..03 | diagnostics, version matrix | `LinuxParserTests`, `LinuxProbeTests`, partial report完了、実環境待ち | Phase 2一部完了 |
| FR-OLLAMA-01 | version matrix, allowlist | `OllamaAdapterTests` fixture完了、0.33.2実環境待ち | Phase 2/3 |
| FR-OPENCODE-01 | version matrix, allowlist | `OpenCodeAdapterTests` JSONC fixture完了、1.18.25探索統合待ち | Phase 2/3 |
| FR-PROFILE-01 | optimization, rule fixtures | `ProfileGoldenTests`、3 profile定義 | Phase 3完了 |
| FR-REC-01..02 | optimization, ADR-0002 | `RuleEngineTests`, `ConflictTests` | Phase 3完了 |
| FR-PLAN-01..02 | allowlist, safe-apply | `OpenCodePlannerTests`, `OllamaDropInPlannerTests`（root helper capability Gateを含む） | Phase 3完了/Phase 4 hardening |
| FR-APPROVE-01 | data-model, safe-apply | `ApprovalTests`, `CoordinatorTests`（plan/report/change hash・期限・apply統合） | Phase 4 core完了 |
| FR-BACKUP-01 | ADR-0005, threat model | backup/crypto/dual-copy/remote recovery/retention/deletion/inventory/evidence retention test群でintegrity、binding、30日/10世代、明示cleanup、fault injectionを検証。実SSH positive recovery/retention/deletion/転送切断とDebian 13 stock crypto/Secret Service/package runtime Gate完了 | Phase 4 core完了 |
| FR-APPLY-01 | ADR-0004, allowlist | atomic/coordinator/helper/PolicyKit/privileged integration/packaging/remote sudo test群でpath、binding、固定operation、fault injectionを検証。Ubuntu 26.04とDebian 13でPolicyKit success/dismiss/deny、package lifecycle、Gate専用systemd操作完了。実Ollama/OpenCode targetは意図的に未変更 | Phase 4 core完了 |
| FR-VALIDATE-01 | allowlist, version matrix | `FileValidatorTests`, `ProductRuntimeValidatorTests`, `OllamaAdapterTests`, `OpenCodeAdapterTests`, `CoordinatorTests`（file hash/JSONC/systemd drop-in構文、service/API/effective environment、再読込、失敗時rollback）。特権/systemd integrationはGate専用unitで完了 | Phase 4 core完了（製品target実Applyは未実施） |
| FR-ROLLBACK-01 | ADR-0005, threat model | coordinator/privileged/journal test群で逆順restore、故障時`RECOVERY_REQUIRED`、SSH切断後のbindingとread-only照合を検証。実remote helper/SSH root evidence取得と`unapplied`照合完了 | Phase 4 core完了（製品target実rollbackは未実施） |
| FR-AUDIT-01 | threat model | `LocalAuditLogTests`, `CoordinatorTests`, `LocalOperationJournalTests`（redaction、hash-chain永続化、tamper/deletion/replay/state reconciliation） | Phase 4 core完了 |
| FR-I18N-01..02 | ADR-0006, gui | `UiI18nTests`（ja/en locale選択、英語fallback、catalog key完全性）、widget即時更新/layoutは後続 | Phase 5一部完了 |
| AC-09/10 | ADR-0003, architecture | `ArchitectureTests`（coreからUIへの逆依存なし）、`GuiPresenterTests`（二重開始/cancel/state transition）、`QtWorkerBoundaryTests`、`QtWindowBoundaryTests`、`QtRuntimeTests`。Ubuntu 26.04/PySide6 6.10.2で別thread、event-loop sentinel、result/cancel、Diagnose vertical slice完了 | Phase 5一部完了 |
| AC-13/14 | allowlist, ADR-0004/0005 | unknown version denial、`LocalOperationJournalTests`（before/after/unknown）、remote統合待ち | Phase 4一部完了 |
| SSH helper prerequisite | ADR-0008, version matrix | `HelperCompatibilityProbeTests`, `OpenSshHostAdapterTests`, `OpenSshUserStagingRunnerTests`, `DiagnoseHostTests`, `OllamaDropInPlannerTests`（local/remote fixed path、absent、symlink、root owner/mode、content hash、canonical package/version/protocol metadata、system OpenSSH固定stat/cat、staging前・invoke直前再検証、fail-closed capability/Plan Gate）、実SSH positive compatibility/user staging/external-terminal sudo/recovery receipt Gate完了 | Phase 4一部完了 |
| Backup crypto/recovery | ADR-0009, threat model | `BackupCryptoTests`, `SecretServiceKeyProviderTests`, `SecretStorageBackendTests`, `RemoteRootKeyProviderTests`, `BackupSettingsTests`, `LocalBackupStoreTests`, `DualCopyPrivilegedBackupStoreTests`, `CoordinatorTests`（AES-GCM/AAD/nonce/tamper/key scope/size、local Secret Service key create-reuse、binding欠落時stable unavailable、remote root key O_EXCL create-reuse/0700/0600/owner/symlink/size/root/path、remote recovery production固定path/root/ownerとsandbox統合、cancel/build default/user persistence/plaintext acknowledgement/restore/approval invalidation）、Ubuntu 26.04とDebian 13 desktopでdefault collectionへのGate専用key create/reload/delete完了 | Phase 4一部完了 |
| Endpoint confinement | ADR-0010, setting allowlist | loopback allow、external/redirect/userinfo deny | Phase 3/4 |
| OpenCode safe edit | ADR-0011, setting allowlist | scalar span、comment、escape、byte-diff fixtures | Phase 3/4 |

Release checklistでは各行を具体的なtest IDへ置換する。設計artifactだけで受け入れ条件を完了扱いにしない。
