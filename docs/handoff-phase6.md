# LLM-Manager Phase 6 引き継ぎプロンプト

以下を新しいチャットの最初のメッセージとして使用してください。

---

LLM-Managerの作業を引き継ぎ、Phase 6 Hardening と MVP Releaseから続行してください。

## 作業場所とGit状態

- `/home/yoshimi/WorkSpace/LLM-Manager`
- branch: `main`
- latest commit: 文書自身のcommitで変わるため、再開時に`git log -1 --oneline`で確認する
- Phase 0〜5完了。Phase 5 closure根拠は`docs/validation/phase5-closure-audit-2026-09-04.md`
- 2026-09-06までのPhase 6変更はcommit `5d3a384`として`origin/main`へpush済み
- 2026-09-07 publication review開始時のworktreeはclean。再開時は`git status --short`とdiffを確認し、以後の変更を保持する
- 2026-09-09にhost system SSH configのroot ownershipが管理者により復旧され、MVP route freeze commit `8854232`を通常のsystem SSHで`origin/main`へpush済み
- 2026-09-09の最新push済み検証commitは`b6ffee1`（candidate environment SBOM / Qt review）。その前は`c204f34`（Debian lifecycle Gate）、`68ad48d`（Ubuntu lifecycle Gate）、`f32ec6b`（再現可能candidate build）。引き継ぎ文書更新commitはこの行の後に増えるため、再開時にHEADと`origin/main`の一致を確認する

## 最新再開サマリー

- **2026-09-10 Debian実display/menu Gate（再開時は本項を優先）**: candidate `4722cfa`由来のlocal debをDebian 13通常Wayland desktopへ一時導入し、GNOMEメニュー検索から起動。UID/GID 1000、英語画面、日本語切替、keyboard focus、Alt+F4通常終了とプロセス不在を確認した。APT simulationで固定12件を導入・purgeし、ホスト保存のpackage/manual baselineと終了値が完全一致。両VMは開始・終了ともrunning、snapshot操作なし。前回のSSH再修復要求はサンドボックス内の観測だけに基づいていたため撤回。実ホストのroot所有設定と通常SSHのUbuntu接続は正常。guest-get-users空でもloginctlにdesktop sessionがあるため両方と実画面で判定する。SBOM archiveのchecksum/identity/inventory/BOM整合性verifierも追加し、既存3 archiveと6 regression testが成功。詳細: `docs/validation/phase6-debian-display-2026-09-10.md`。次は通常SSHのGUI切断照合と最終release setの残Gate。現在・次ともPhase 6。

- **2026-09-09 `0.1.0` candidate environment SBOM / Qt review（再開時は本項を優先）**: commit `4722cfa`由来の同一candidate setでUbuntu local/remoteとDebian localのinstalled環境CycloneDX 1.6 evidenceを採取。Debianは2248 package・copyright欠落0、Ubuntu localは1907、remoteは1908で、開始前からある非依存Brave 2件だけが標準copyright欠落。両OSのQt binding/module/plugin 23 packageとPySide6/Shiboken runtime 2 packageに欠落なく、package/file/ELF/runtime plugin/source versionと原文を固定し、PySide6のQt GPL exceptionを含む既存notice/SBOM表記との整合を再確認した。3 archiveの内部checksumを全件検証。Ubuntuは一時snapshotを各composition間でrevert後に削除しrunningへ復帰。Debianはcandidate＋依存11件だけを明示purgeし、2236 packageと集合SHA-256 `d4b4d64a2dd5ca6436291fe1425aba368765ae8d63d26ea01251184da685d35e`へ復帰、shut off。これは`UNRELEASED` candidateのpre-final evidenceで、final artifact再採取は残件。通常system SSH configは再びowner/mode不正でfail closedしたため変更せずSSH Gate保留、Debianに通常loginはなく実display/menuも保留。詳細: `docs/validation/phase6-0.1.0-candidate-environment-sbom-qt-2026-09-09.md`。現在・次ともPhase 6。

- **2026-09-09 `0.1.0` Debian lifecycle Gate（再開時は本項を優先）**: commit `4722cfa`由来のlocal candidateを、package未導入のDebian 13で検証。fresh install、reinstall、remove、再fresh install、purge、`dpkg -V`、UID 1000隔離import、Debian stock PySide6 6.8.2.1のoffscreen Qt起動、owner/modeが成功した。pflash NVRAM非QCOW2のため内部snapshotは変更前に拒否され、NVRAMを変更せずexact-cleanupへ切替。APT simulationでcandidate＋新規依存11件を固定し、`autoremove`なしで全12件を明示purge、artifactも削除した。終了時は2236 package、集合SHA-256 `d4b4d64a2dd5ca6436291fe1425aba368765ae8d63d26ea01251184da685d35e`が開始値と完全一致し、SSH serverは未導入のまま、VMは開始時どおりshut off。active desktopなしのため実display/menu、旧版なしのためupgrade、`UNRELEASED`解除後の最終artifact再実行は残件。詳細: `docs/validation/phase6-0.1.0-debian-lifecycle-2026-09-09.md`。現在・次ともPhase 6。

- **2026-09-09 `0.1.0` Ubuntu lifecycle Gate（再開時は本項を優先）**: commit `4722cfa`由来のlocal candidate（SHA-256 `25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181`）をUbuntu 26.04一時snapshot内で検証。旧`0.1.0~dev0-1`からのupgrade、同一version reinstall、remove、fresh install、purge、`dpkg -V`、隔離import、UID 1000 offscreen Qt起動、owner/modeが成功した。remove/purgeはpackage-owned pathだけを消し、既存依存とdpkg管理外root backupを保持。receipt/retention hashは全境界で開始値と一致した。検証用deb/logを削除してsnapshot revert後、旧package、1913 packageと集合SHA-256 `b9d31c0708f9bba521ddae6afc272816fe53affb80291ad9665607412ea93008`、backup hashの完全一致を確認。一時snapshotだけを削除し、既存Phase 4 snapshotを保持、Ubuntuは開始時どおりrunning。これは`UNRELEASED` candidateのpre-final Gateで、Wayland実display/menuと最終artifact再実行は残件。詳細: `docs/validation/phase6-0.1.0-ubuntu-lifecycle-2026-09-09.md`。現在・次ともPhase 6。

- **2026-09-09 `0.1.0` candidate composition（再開時は本項を優先）**: commit `4722cfa` のtracked sourceからlocal/remote debを独立2回build・verifyし、両方byte-for-byte一致。local SHA-256 `25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181`、remote `45dcd8eb852317aed1da212a7bb0c1f3d008aee5d1aae38b09f980df8e56a1d1`。展開監査で実行fileはlocal 5/remote 1の固定launcherだけ、ELF/shared library、bytecode cache、third-party vendored moduleなし。初回の`git archive`は既定`tar.umask=0002`でtracked executableが0775となり、build内mode test 5件が意図どおり拒否。この結果は破棄し、`git -c tar.umask=0022 archive`と`set -eu`で再実行した。採用artifactは`/tmp/llm-manager-release-candidate-4722cfa/`に限定し、重複/失敗build treeはcleanup済み。`UNRELEASED`解除後の最終artifactで再実行が必要。詳細: `docs/validation/phase6-0.1.0-candidate-composition-2026-09-09.md`。現在・次ともPhase 6。

- **2026-09-09 MVP version freeze（再開時は本項を優先）**: release versionを`0.1.0`に固定。Python package、Debian changelog/remote control、両helper metadata、両SBOM、artifact verifier、local/remote helper compatibility allowlist、packaging手順を同期し、version consistency Gateをstable/dev両形式対応にした。最初focused実行で旧`dev0`置換fixtureの無効化を1件検出し、`0.1.0`→`0.2.0`改変へ修正後、focused 23件と全791件（753成功・38 expected skip）、必須静的検査成功。`debian/changelog`は最終OS/SBOM/署名Gate前のため`UNRELEASED`を維持。詳細: `docs/validation/phase6-version-freeze-2026-09-09.md`。現在・次ともPhase 6。

- **2026-09-09 release version consistency preflight（再開時は本項を優先）**: SSH設定復旧後、`8854232`を`origin/main`へ通常経路でpushした。Ubuntu 26.04はrunning/IP `192.168.122.48`、logged-in userなし、Debian 13は`shut off`。通常system SSHでUbuntuのUID 1000へread-only接続でき、3つのOpenCode target候補は不在、remote helperは前回cleanupどおり未導入。管理者認証なしにSSH実機Gateを拡張せず、release version同期testを追加した。Python版、Debian版、changelog、remote control、両helper metadata/SBOM/verifier、production compatibility allowlistの不一致を検出する。version自体は最終Gate前のため`0.1.0.dev0`/`0.1.0~dev0`を維持。focused 8件、host全791件（753成功・38 expected skip）、必須静的検査成功。詳細: `docs/validation/phase6-release-version-consistency-preflight-2026-09-09.md`。現在・次ともPhase 6。

- **2026-09-08 MVP production route freeze（再開時は本項を優先）**: MVP releaseのmutation scopeをlocal user/SSH user Applyとlocal user/local root manual restoreに固定した。local root Applyはactionable Ollama ruleなし、SSH root ApplyとSSH user/root restoreは専用protocol未完成のためscope外とし、実装とproduction allowlistのI/O前fail-closedを維持。requirements、MVP scope、README、roadmap、traceability、release checklistを同期した。focused 12件と全790件（752成功・38 expected skip）、必須静的検査は成功。両VMは`shut off`、host SSH configは依然`nobody:nogroup`/0777のため実機Gateは行っていない。詳細: `docs/validation/phase6-mvp-route-scope-freeze-2026-09-08.md`。現在・次ともPhase 6。

- **2026-09-08 local root手動restore公開（再開時は本項を優先）**: commit `9fe071d` のfresh dev deb（SHA-256 `6e2a70515f38554bc35e5151ff6cc847fc26d4a2d864ba0226c975925d89d984`）をUbuntu 26.04一時snapshotへ導入し、UID 1000 active Wayland sessionでreview/execute各PolicyKit actionの明示cancel（126）と認証成功を確認した。正規request `3e5fcea00d06ee7fab8f34a3938ba13900b4bdd3e23974c0deb2d7b639e6fa1a`は復元・systemd restart・loopback API検証を完了して`committed`、read-only statusも同一resultを返した。root-owned 0600 review/attempt/result、strict 4-event audit chain、target root:root 0644と元hashを照合。最初の`Type=simple` fixtureは起動直後のAPI競合を`service_validation_failed`として正しく記録し再送せず、`Type=notify`の別backup/requestで完走した。snapshot復元後、旧package `0.1.0~dev0-1`と全fixture不在、port 11434不在を確認し、両VMを`shut off`、一時snapshotを削除。production restore allowlistへ`LOCAL_ROOT`を追加し、local root ApplyとSSH restore/root Applyはfail closedを維持。公開後は全790件（752成功・38 expected skip）と必須静的検査、fresh dev deb build/verifyに成功し、archive内allowlistを確認。最終dev deb SHA-256 `7da8c5965e0c4e205dad1a82a6cf1cfdd21dae4d9b4f6fdc8479fa96a6876e3c`。詳細: `docs/validation/phase6-root-restore-interactive-policykit-2026-09-08.md`。現在・次ともPhase 6。

- **2026-09-08 local root Apply理由監査（再開時は本項を優先）**: 両VMは`shut off`でactive desktop PolicyKit Gateは保留。local root ApplyのPolicyKit/composition/rollback/origin capture/installed OS境界は完成済みなのに拒否理由が`composition_missing`のままだったため、実際のblockerに合わせ`local_root_apply_rule_pending`へ変更し英日表示・4 route testを同期した。設定allowlistは推奨根拠ではなく、未検証閾値やhardware/runtime根拠なしにOllama設定ruleを追加していない。production allowlistは`LOCAL_USER`/`SSH_USER`のみでfail closedを維持。全790件（752成功・38 expected skip）と必須静的検査成功。詳細: `docs/validation/phase6-local-root-apply-reason-audit-2026-09-08.md`。現在・次ともPhase 6。

- **2026-09-07 publication review（再開時は本項を優先）**: commit `5d3a384` を `origin/main` へpush済みでworktreeはclean。通常画面登録、production allowlist、既定拒否、SSH拒否、PolicyKit action/launcher、package検証を横断reviewし、`LOCAL_ROOT`手動restoreはactive desktop PolicyKit prompt/auth/cancel evidenceが揃うまで非公開継続と確定した。2026-09-07確認時、Ubuntu 26.04はrunningだがguest-agentのlogged-in userは0、Debian 13は`shut off`。passwordやsynthetic loginを使わずGateを保留した。host SSH configは依然`nobody:nogroup`・0777で、`-F /dev/null`をproduction根拠にしていない。package/target/service/root state/key/PolicyKit/SSH変更なし。詳細: `docs/validation/phase6-root-restore-publication-review-2026-09-07.md`。次は通常ログイン済みactive desktopでreview/execute各actionのprompt/cancel/authとimmutable status照合を実施する。現在・次ともPhase 6。

- **2026-09-07 recovery手順acceptance**: Apply `recovery_required`、restore `failed`/`unknown`、backup key喪失、片側copy/key喪失を実装状態機械と利用者ガイドで照合した。`failed`と`unknown`の意味、健全側の保全、mutation/cleanup停止、同一IDや新規keyでの再生成禁止を明確化し、release checklist項目を完了した。focused 81件は80成功・明示Secret Service desktop Gate 1 expected skip。詳細: `docs/validation/phase6-recovery-procedure-acceptance-2026-09-07.md`。production routeや実環境は変更していない。

- **2026-09-07 public route文書監査**: README/recovery guideの古い「全root/SSH routeはprotocol未完成」という含意を修正。local root手動restoreは専用実装・disposable OS Gate済みでactive desktop PolicyKit公開Gate待ち、local root Applyはactionable Ollama rule待ち、SSH root ApplyとSSH user/root restoreは専用protocol待ちとして区別した。availability allowlistと実装は変更していない。詳細: `docs/validation/phase6-public-route-documentation-audit-2026-09-07.md`。

- **最新slice（gated main window＋Ubuntu Qt）**: 通常Backup画面へ専用system restore workflow callbackを登録したが、別の`requires_root=True` availability Gateを必須化し、省略時も既定拒否、production allowlistは`LOCAL_USER`のみを維持。入口はI/O前に無効で、拒否理由を実装済みprotocolに合わせ`local_root_restore_release_gate_pending`へ更新した。Ubuntu 26.04実PySide6 Gate初回で既存change-plan期限のsub-ms切捨て同期再帰を検出し、正の残時間は最低1ms timerへ修正。最終source artifact SHA-256 `63a7887ec1550ea613ba0fb4ee29fdbffbef5ad2c3092bcef510907e6787e82c`、UID 1000 offscreen Qt 42件（40成功・inverse boundary 2 skip）、host全789件（751成功・38 PySide6 skip）、必須静的検査成功。fresh dev deb build/verifyと収録確認も成功、SHA-256 `0ee77ebd3389e0120d3c037dd48c3246a0c90adda4b4190532277a62f21913d5`。active user desktopはなくmanager session＋GDM greeterのみのためinteractive PolicyKitは未実施。artifact/server/build copy cleanup済み、Ubuntu/Debianとも`shut off`、package/target/service/root state/SSH未変更。詳細: `docs/validation/phase6-root-restore-main-window-qt-2026-09-06.md`。次はactive desktop interactive PolicyKit prompt/auth/cancel Gateと最終公開review。通常root routeは非公開、全変更未コミット。現在・次ともPhase 6。

- **最新slice（root inventory/workflow）**: root backup storeの件数上限32・ID順・全entry整合性・読取り前後不変を検査するread-only inventoryを追加。orphan/pending/未知file/過多は全一覧を拒否し、key ID/ciphertext/payloadは返さない。専用review CLI/clientへ`list`を追加し、caller/host/schema/hash/timeを厳密照合。UID/hostを共有するone-shot inventory sessionからreview保存、同一requestの最終execute sessionまでを明示Qt workflowで接続した。選択・review・最終同意は別工程で自動遷移/再送なし。通常menu/allowlistへは未登録。要求間排他は特権processを外部validation中に保持せず、各mutation lock＋before-hash＋immutable receipt＋不一致時`RECOVERY_REQUIRED`を正式方針とした。新規11 test、全785件（750成功・35 Qt skip）、必須静的検査、fresh deb build/verify成功。SHA-256 `60c21311c9952ad7d3b557a12112ef74d6c351e7dc3cf714c1c253ad923f637a`。詳細: `docs/validation/phase6-root-restore-inventory-workflow-2026-09-06.md`。次はgated main-window登録と対応VM Qt/active desktop PolicyKit Gate。実環境未変更、通常route非公開、全変更未コミット。現在・次ともPhase 6。

- **最新slice（installed Apply capture OS Gate）**: SHA-256 `8e2897a083ab7b7ae86d7136cc8a2e58f41b84c2906ebd8d1e3c8b0530f73615`のdev debをUbuntu 26.04一時snapshotへ導入。通常user setupは`root_required`、root明示setupは成功、再実行は鍵hash不変で拒否。synthetic `PKEXEC_UID=1000`のinstalled helperで認可済みlocal Applyを実行し、対象lock内で元drop-inをAES-GCM採取・復号照合後に置換、terminal receiptとroot-owned 0600 evidenceを確認。同一request replayは拒否されtarget/evidence不変。snapshot復元後、旧`0.1.0~dev0-1`、restore state、target、artifact不在を確認。VMはshut off、一時snapshot削除済み。詳細: `docs/validation/phase6-root-apply-capture-installed-os-gate-2026-09-06.md`。次は要求間排他のscope判定と通常GUI inventory/review/execute接続、active desktop PolicyKit Gate。通常GUI非公開、全変更未コミット。現在・次ともPhase 6。

- **最新slice（2026-09-06 Apply capture/setup）**: local production Apply helperへorigin採取を接続。独立local host・完全binding・操作順をreceipt前に検査し、対象lock内でstaging確認→既存固定key読取り→AEAD採取/永続化→期限/hash再照合→write/service。鍵欠落や採取失敗時はwriteを停止し、証拠/receiptを保持。管理者専用`llm-manager-restore-setup initialize`とisolated launcher/manpage/deb検証を追加。固定private dirの空状態だけを排他初期設定し、既存key/backup/history/partial状態は上書きしない。新規15 test、final build全774件（739成功・35 Qt skip）、必須静的検査・deb verify成功。SHA-256 `8e2897a083ab7b7ae86d7136cc8a2e58f41b84c2906ebd8d1e3c8b0530f73615`。詳細: `docs/validation/phase6-root-apply-capture-setup-2026-09-06.md`。次はこのartifactでinstalled setup＋認可Apply採取のdisposable OS Gate。要求間排他・通常GUI接続・interactive PolicyKitは残件。実環境未変更、通常GUI非公開、全変更未コミット。現在・次ともPhase 6。

- **最新slice（再開時は本項を優先）**: root復元の公開条件をコードと照合し、通常GUI非公開の継続を確認。前回のinstalled valid OS Gateは成功済みだが、interactive PolicyKitに加え、Applyからのorigin採取、明示provisioning入口、要求間排他、通常GUIの一連の接続も残件。execute clientのtimeout/遅延cancelが126/127より優先されない問題を4条件で再現し、unconfirmed＋status照会へ修正。関連17 test成功。詳細: `docs/validation/phase6-root-restore-route-review-2026-09-06.md`。次は認可済みApplyのorigin採取とprovisioningの接続契約。VMは両方shut off、実環境未変更、deb再buildなし、全変更未コミット。現在・次ともPhase 6。

以下は過去sliceの記録。「最新slice」や残件の記述は記録時点の状態であり、上記と末尾の追記を優先する。

- 最新slice: root復元の非特権one-shot execute clientを追加。exact requestを現在時刻/UID/host/hashで検査し、固定pkexec/execute entryを180秒・stream別32 KiB上限で呼ぶ。正常terminal resultを厳密照合し、起動後のtimeout/cancel/runner障害/不正応答/exit 1は専用unconfirmedとして自動retryせずstatus照合を要求する。126/127だけ実行前結果として区別。新規9 test（client→実CLI→一時coordinator統合含む）、host全745 test（714成功・31 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-execute-client-2026-09-06.md`。通常GUI/root mutation routeは非公開。最終同意GUI、provisioning、実PolicyKit/installed deb/service/OS Gate、要求間排他は残件。前sliceのdebは本client追加前。実環境変更なし、全変更未コミット。現在・次ともPhase 6。

- 前slice: root復元専用execute CLI、独立PolicyKit action、isolated launcher、manpage、deb収録/検証を追加。canonical requestをcomposition I/O前に独立UID/host/hash/期限で検査し、保存済みterminal resultのbindingを再検査。failed/unknownはattention、result永続化失敗はexecution_unconfirmedとして自動retryしない。新規8 test、host全736 test（705成功・31 skip）、必須検査とdev deb build/verify成功。artifact SHA-256 `5b8606b11299932e102c0c3b9e3c23fe88d0e2710c428cb4f9ed19d4ee9515db`。詳細: `docs/validation/phase6-root-restore-execute-cli-2026-09-06.md`。通常GUI/root mutation routeは非公開。非特権execution client/最終同意GUI、明示provisioning、実PolicyKit/installed deb/service/OS Gate、要求間排他は残件。実環境変更なし、全変更未コミット。現在・次ともPhase 6。

- 前slice: root復元の固定production compositionとStoredRootRestorePreflightを追加。backup/key/source/store/audit/serviceを接続し、root guard・audit chain事前検査・全FDの例外時解放を実装。新規6 test（実store/復号/target/auditを使うport統合含む）、host全728 test（697成功・31 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-composition-2026-09-06.md`。compositionは認可ではなく、専用実行CLIは未公開。要求間排他・provisioning・PolicyKit/installed deb/OS Gateも残件。実環境変更なし、全変更未コミット。現在・次ともPhase 6。

- 前slice: root復元専用audit adapterと固定openerを追加。root metadata/no-follow、hash chain/HEAD、request開始終了対応、排他、event先行/fsync/HEAD更新、中断証拠のfail closedを実装。新規9 test（実一時復元coordinator接続含む）、host全722 test（691成功・31 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-audit-2026-09-06.md`。専用実行認可/CLIのproduction composition、要求間排他、provisioning、実PolicyKit/installed deb/OS Gateは残件。root mutation非公開、実環境変更なし、全変更未コミット。現在・次ともPhase 6。

- 前slice: Ubuntu 26.04/Python 3.14.4/PySide6 6.10.2でoffscreen関連52 testを実行、51成功・1 expected skip。新規GUI 2件（履歴照会の重複抑止、照会中close/遅延結果破棄）も成功。詳細: `docs/validation/phase6-root-status-qt-ubuntu2604-2026-09-06.md`。package追加なし、host/guest検証物cleanup済み、両VM shut off確認。実PolicyKit/installed deb/実display/Debian Qt Gateは未完了。次もPhase 6: 専用実行認可/CLI・production audit・要求間排他・provisioning・最終Gate。root mutation非公開、全変更未コミット。

- 前slice: 非公開root review dialogへ明示・単発の履歴照会ボタンを追加。保存成功/結果不明後にexact requestでstatus clientを非同期呼出しし、重複操作・再送・遅延成功を抑止。英日で履歴/unknown/照会失敗を区別する。新規session 3 test成功、Qt 2 testはhost PySide6不在で未実行。host全713 test（682成功・31 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-status-gui-2026-09-06.md`。次は対応VMでQt Gate。専用実行認可/CLI・production audit・要求間排他・provisioning・PolicyKit/OS Gateも残件。通常menu/root mutation非公開、実環境変更なし、全変更未コミット。現在・次ともPhase 6。

- 前slice: root復元の非特権status clientを追加。exact intentのUID/host/hashと応答schema・時刻・attempt/result digest・state/attentionを検証し、期限切れ履歴を単発照会する。新規7 test（実CLI＋一時store統合含む）、host全708 test（679成功・29 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-status-client-2026-09-06.md`。GUI接続、専用実行認可/CLI・production audit・要求間排他・provisioning・PolicyKit/OS Gateは残件。root mutation非公開、実環境変更なし、全変更未コミット。現在・次ともPhase 6。

- 前slice: 専用review CLIへread-only `status request-id request-sha256`とstore reconciliationを追加。独立caller UID/host/要求hashを同一shared lock下で照合し、期限切れ後も履歴を読む。鍵/backup/current target不要、attempt-onlyはunknown、欠落/破損を未実行扱いせず、自動retryなし。新規8 test、host全701 test（672成功・29 skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-status-2026-09-06.md`。専用実行認可/CLI・production audit・非特権status client/GUI・要求間排他・provisioning・PolicyKit/OS Gateは残件。root mutation非公開、実環境変更なし、全変更未コミット。現在・次ともPhase 6。

- 前slice: 既存Apply helperと専用root復元を同じtarget directory flockへ接続。helper要求内のbefore-hash確認・書込み・rollback operation・service操作を排他し、競合/中断staging/取得後期限切れを拒否する。実flock・別process・CLI receipt/replayを含む新規10 test、host全693 test（664成功・29 skip）、必須検査成功。詳細: `docs/validation/phase6-root-target-lock-2026-09-06.md`。排他はhelperの1要求単位で、backup採取〜外部validation〜別rollback要求をまたぐtransaction、origin capture接続、旧版/外部mutator協調は未完了。専用root実行認可/CLI・provisioning・PolicyKit/OS Gateも残件。root route非公開、実設定/service/SSH/VM状態変更なし、全変更未コミット。現在・次ともPhase 6。

- 前slice: root復元レビュー専用の同意sessionとQt dialogを追加。現在/backup metadata・期限・hashを表示し、明示同意後に専用clientでレビューのみ保存する。期限/同意解除/失敗/closeで無効化、重複保存と自動retryを抑止。通常メニューは未公開。host全683 test（654成功・29 skip）、Ubuntu 26.04/PySide6 6.10.2のoffscreen関連22 test（21成功・1 expected skip）、必須検査成功。詳細: `docs/validation/phase6-root-restore-review-dialog-2026-09-06.md`。実PolicyKit/installed deb・実display・Debian Gate、root専用実行認可/CLI、全mutator lock、provisioningは未完了。次もPhase 6。実設定・service・SSH変更なし、VM検証物cleanup済み、全変更未コミット。

- 前slice: root復元レビュー専用CLIを呼ぶ非特権clientを追加。固定pkexec/専用entry、120秒timeout、32 KiB応答上限、canonical応答、UID/host/対象/期限/hash、保存receiptを検証する。自動retryなし。実CLIと一時root storeの往復を含む新規9 test、全670 test（647成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-review-client-2026-09-06.md`。GUI consent/production composition、実PolicyKit、専用実行認可、全mutator lock、OS/Qt Gateは未完了。root mutation route非公開、実設定・service・VM・SSH未操作、全変更未コミット。次もPhase 6。

- 前slice: 専用root restore review CLIと固定dir_fd composition、独立PolicyKit action review-system-restore、isolated launcher、deb install/manpage/検証scriptを追加。preview/approveのみで復元実行はない。全661 test（638成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-review-cli-2026-09-06.md`。実PolicyKit/installed deb/GUIは未検証。次もPhase 6: GUI consentと呼出し、専用実行認可/CLI、全mutator lock統合、OS/Qt Gate。root mutation route非公開、実設定・service・VM・SSH未操作、全変更未コミット。

- 前slice: root側review再計算producerを追加。独立caller/host、root-owned origin、現在のtarget、AEADを照合して専用reviewを保存する。元Apply manifest hashをoriginとAEADへ追加。新規14 test、全653 test（630成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-review-2026-09-06.md`。専用PolicyKit action/CLIとGUI consentは未接続であり、既存Apply actionを流用しない。次もPhase 6: 専用認可/dispatch、全製品mutatorの同一target lock、PolicyKit/OS/Qt Gate。実設定・service・VM・SSH未操作、root route非公開、変更は未コミット。

- 前slice: 固定source parent openerとRootRestoreOllamaServiceを追加。絶対pathのsystemctl/curl、effective env・loaded/active/running、loopback限定、curlrc/proxy/redirect無効、Ollama 0.33.2/API schemaを検証。coordinatorへ復元内容を渡し、実file復元＋serviceロジック＋模擬commandで統合。全639 test（616成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-service-2026-09-06.md`。次もPhase 6: trusted review認可producer、privileged composition/CLI、全製品mutatorの同一target lock、PolicyKit/OS/Qt Gate。実service/VM等は未操作、production未接続、未コミット、root非公開を維持。

## 2026-09-05 再開サマリー（履歴）

- 前slice: 専用root restore coordinator/単一target executorを追加。target flock下でpreflight→attempt→開始audit→最終照合/期限guard→復元→service/target検証→終了audit/result。実一時fileでreplace/create/removeとfault injection、新規14 testを含む全628 test（605成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-execution-2026-09-05.md`。次もPhase 6: 固定source opener、trusted review認可producer、実service validation、privileged composition/CLI/PolicyKit/OS/Qt Gate。既存Apply/外部root操作は本target flockへ未統合。実環境未操作、production未接続、root非公開、未コミットを維持。

- 前slice: `RootRestoreStore`でreview/attempt/resultをroot-owned canonical不変recordへ保存。別hash同ID、attempt-only/failed/unknown再試行、orphan/pending/改変は拒否。統合preflightのreview/attempt fixtureを実fileへ置換し、attempt後の再preflight拒否を確認。全614 test（591成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-store-2026-09-05.md`。次もPhase 6: 専用実行coordinatorと対象の最終照合/排他/audit境界を構築する。trusted review producerの認可経路、executor/service/crash/OS Gateは未完了。実環境操作なし、未コミット、root route非公開。

- 前slice: root key明示provisioningとorigin verifierを追加。key/readyの排他公開、get時は作成せずstrict shared read、固定key opener、reviewのorigin/source hash必須化、復号後の証拠再読込を実装。実一時fileでprovisioning→capture→AEAD→preflightまで統合（review/attemptだけfixture）。全600 test（577成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-key-origin-preflight-2026-09-05.md`。次もPhase 6: trusted review/immutable attempt/resultの保存形式とstrict adapterを整備する。実環境のkey/VM等は未操作、production未接続、未コミット、root restore非公開を維持。

- 前slice: root backupの固定target採取、local_root scopeのAES-GCM、復号照合、payload先行/record最後の排他公開を追加。root keyはstrict readのみで自動作成なし。pending/orphan/既存IDは上書き・自動cleanupせず拒否。reader shared/capture exclusive lockは独立open descriptionを使用。全589 test（566成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-backup-capture-2026-09-05.md`。次もPhase 6: key provisioningと固定source/key opener、trusted origin/review/attempt adapterを整備してpreflightへ接続する。production helper/GUIは未接続、root route非公開。実環境操作なし、未コミット。ciphertext上限はBase64 envelopeに合わせMAX_ENVELOPE_BYTESへ修正済み。

- 前slice: root backup origin evidence形式とread-only readerを追加。固定`/var/lib/llm-manager/local-root-restore/backups`、root:root 0700/0600、canonical record、opaque ciphertext hash、dir_fd/O_NOFOLLOW、全ancestor権限、size/cancel、inode差替えを検査。実一時fileの12 testを含む全575 test（552成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-backup-evidence-reader-2026-09-05.md`。次もPhase 6: root採取/暗号化/atomic publication producerと鍵境界、origin照合/復号adapterを整備する。readerはpreflight未接続、ciphertextのAEAD/平文真正性未検証。user manifest importや旧backup自動変換は設けない。実環境操作なし、未コミット、root restore非公開を維持。

- 前slice: local root restoreのread-only preflight orchestrationを追加。root側review/backup/current/attemptのport契約を定義し、backup検証前後の再照合、全7 read後のcancel/期限、rehash済み偽要求の拒否をsandbox 10 testで確認。全563 test（540成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-local-root-restore-preflight-2026-09-05.md`。次もPhase 6: root採取のbackup origin証拠producer/保存形式を確定し、strict read-only adapterへ進む。現preflightは注入portのみでproductionのroot store/復号/lock/executorには未接続。戻り値はauthorityやrequest予約ではない。実環境操作なし、未コミット、root route公開/MVP scope変更なし。

- 前slice: local root手動restoreの専用intent codecを追加。固定target、current/backup hash+metadata、caller UID/host、manifest/inventory/preview/approval、16 KiB/5分期限をcanonical requestへ束縛する。I/O・特権dispatch・認可発行は未接続。全553 test（530成功・23 skip）、compileall/shell/desktop/diff成功。専用契約: `docs/local-root-restore-protocol.md`、検証: `docs/validation/phase6-local-root-restore-protocol-2026-09-05.md`。次もPhase 6: root-owned backup/inventory evidenceの保存方式を確定し、read-only preflightへ進む。user-owned manifest/hashだけをroot authorityにせず、既存Apply rollback protocolを流用しない。実環境操作なし、変更は未コミット。root route公開・MVP scope変更は行っていない。

- 前slice: root route監査で、Ollama専用drop-inの一部設定変更が未選択設定を削除する問題をregressionで再現し修正した。既存literal assignment・コメント・改行を保持し、未知directive/重複key/escape/継続行等は計画生成を拒否する。全544 test（521成功・23 skip）、compileall/shell/desktop/diff検査成功。詳細: `docs/validation/phase6-root-drop-in-preservation-2026-09-05.md`。実設定・VM操作なし。MVP scopeとroute availabilityは変更していない。次もPhase 6: 未完成routeの専用契約、scope/version判断、実display/SSH/最終artifact Gate。保存済みdeb/SBOMは本修正前のcodeに対する証拠である。

- 前slice: Ubuntu 26.04でremote helperの修正後dev deb（SHA-256 `259eb7e11cd912bf0eddd287413e3183f57cd0cfcbe290616933724816f88bb7`）を一時snapshot内へ導入し、通常userからinstalled環境SBOMを採取した。1908 package、copyright欠落は既存Brave関連2件。snapshot復元後のpackage版・manual一覧一致と一時artifact不在を確認し、snapshot削除・VM停止済み。詳細: `docs/validation/phase6-remote-sbom-2026-09-05.md`。Debianは起動していない。次もPhase 6: scope/version判断、ログイン済みDebian実display、最終artifact lifecycleとrelease SBOM。SSH設定は未修復。既存変更は未コミットで保持する。

- 前slice: 両VMで同一local dev debのinstalled SBOM/copyright/Qt ELF evidenceを採取・archive保存済み。Debian 2248件・欠落なし、Ubuntu 1907件・既存Brave関連2件の標準copyright欠落。Qt/PySide6の欠落なし。原文reviewでGPL例外の省略を発見し、notices/直接依存SBOMを修正。Debianは追加12件をexact purge、Ubuntuはsnapshot復元し、package版とmanual一覧が開始前と一致。両VMはshut off。詳細: `docs/validation/phase6-vm-sbom-qt-review-2026-09-05.md`。最終release SBOM/全license obligationは未完了。次はremote helper環境採取、scope/version判断、ログイン済みDebian実display、final lifecycle。

- 追加slice: `packaging/collect-installed-sbom.py`を整備。host全2519 packageを採取しcopyright欠落5件を検出（期待exit 2）、CycloneDX 1.6 schema検証成功。全537 test（514成功・23 skip）。これはhost smokeであり対象VMのresolved-environment release SBOM/Qt license reviewは未完了。詳細: `docs/validation/phase6-installed-sbom-2026-09-05.md`。次は最終artifactとの紐付け採取とQt原文review。VMは停止のまま、SSH configも未変更。

- 現在・次の作業はPhase 6。2026-09-09のチャット移行後はこのファイルを基点に再開する
- 最新の全検査は791件完走（753成功・38 expected skip）。compileall、local/remote packaging shell syntax、desktop validation、両SBOM JSON parse、`git diff --check`も成功。以後のUbuntu/Debian lifecycle sliceは文書変更だけで、各commit前に`git diff --check`成功
- hostの実稼働Ollama 0.33.2 / OpenCode 1.18.25を使ったread-only production local診断は5/5 sampleが`complete`。実設定、service、model、SSHは変更していない
- 安全検査済みの`~/.opencode/bin/opencode`をproduction discoveryとlocal user Apply validationへ追加した。任意PATH、root、SSH経路へは拡張していない
- local user Applyはhost・Ubuntu 26.04・Debian 13でcommit/rollback/recovery-requiredを各5回、計45 sample成功。各環境はexact cleanup済み
- subprocessのstdout/stderr EOF後にもcancel/deadlineを監視する修正と、有限のcancel非協力区間に対するGUI終了待機表示・操作抑止を実装し、実Qt Gateまで完了
- Ubuntu 26.04 VMは`running`、Debian 13 VMは`shut off`。UbuntuのPhase 6一時snapshotは削除し既存`phase4-pre-local-deb-20260831`だけを保持。Debianの内部snapshotはpflash NVRAM非QCOW2のため変更前に拒否され、作成されていない。両Gateの一時artifactと追加packageはexact cleanup済み
- production system SSHは2026-09-10に実ホスト側で正常と再確認した。symlinkはroot所有、参照先root:root 0644、通常system SSHでUbuntu UID 1000への接続成功。前回サンドボックス内で観測したowner不正をホストの再発と断定した記述は撤回する。設定変更は不要。
- commit `4722cfa`由来の採用candidateはhostの`/tmp/llm-manager-release-candidate-4722cfa/`にlocal/remote各1 artifactだけを0644で保持。local SHA-256 `25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181`、remote `45dcd8eb852317aed1da212a7bb0c1f3d008aee5d1aae38b09f980df8e56a1d1`
- candidate環境SBOM採取とDebian実display/menuはpre-final Gate済み。全license obligationは未完了。次は通常system SSHの完成GUI disconnect/reconciliation、`UNRELEASED`解除判断とfinal artifact再build/lifecycle/SBOM。

## 完成済みproduction routeと安全境界

- production GUIで公開済み: local user Apply、SSH user Apply、単一local OpenCode target手動restore、local root Ollama手動restore
- local root ApplyはcompositionとQt Gate済みだが、default rule catalogから根拠あるactionable Ollama recommendationへ到達する規則が未確定のためfail closedを維持する
- SSH root ApplyとSSH user/root restoreは専用protocol不足の固定理由でI/O前にfail closed
- SSH root/restoreを既存SSH user protocolの単純拡張として推測実装しない
- SSH切断時は同一immutable resultだけをread-only再照合し、mutationを自動retryしない

## 今回完了したGUI deb slice

正式local debへ以下を追加した。

- `/usr/bin/llm-manager`: 非特権GUI用のdistribution-owned `/usr/bin/python3 -I` launcher
- desktop entry: `packaging/desktop/io.github.nbe03xxx.llm-manager.desktop`
- scalable SVG icon: `packaging/icons/io.github.nbe03xxx.llm-manager.svg`
- PySide6 QtCore/QtWidgets runtime dependency
- `packaging/verify-deb.sh`のlauncher/desktop/icon/owner/mode/fixed reference検査
- `tests/test_distribution.py`のdistribution境界test

PolicyKit actionは引き続き`/usr/bin/llm-manager-helper`だけを許可し、GUI全体をrootで起動しない。

最終composition artifact:

- package: `llm-manager 0.1.0~dev0`
- SHA-256: `a85915eb39d7f73d7d6bf2f125a2ed90cb62cb322591ae9c4ea963266656509f`
- 一時build場所は永続成果物として扱わず、必要ならworkspace外の新しい`/tmp` copyで再buildする
- 詳細: `docs/validation/phase6-gui-deb-composition-2026-09-05.md`

## PySide6 version監査の重要事項

Debian 13 stockはPython 3.13.5 / PySide6 6.8.2.1。従来の一律`PySide6 >= 6.8.6`では正式Debian対象の依存が解決不能になる矛盾を検出して修正した。

- Debian system package + Python 3.13の組合せだけはPySide6 6.8.2.1以上
- Python 3.14環境はPySide6 6.8.6以上を維持
- `debian/control`、requirements、version matrix、MVP scope、ADR-0007をこの区別へ更新済み
- 未検証の任意OS/Python/PySide組合せへ一般化しない

## Ubuntu 26.04 GUI deb実機Gate

- 一時internal snapshot内でAPT installとPySide6 6.10.2依存解決成功
- UID 1000通常ユーザーから既存Wayland sessionへ日本語GUIを実描画
- launcher/helper 0755、desktop/icon 0644、root ownership確認
- 同版reinstall成功、purgeと配置物不在確認
- snapshotへrevert後、元の`llm-manager 0.1.0~dev0-1`を確認し、一時snapshotを削除
- Gate用deb/log/package変更はsnapshot外へ残していない

Ubuntu VMのSSH Server、VM user `authorized_keys`、host `known_hosts` entryは後続SSH Gateに必要なためユーザー判断で維持する。VM IP `192.168.122.48`は動的DHCPなので、再開時はguest agent/leaseから再取得する。

## Debian 13 GUI deb実機Gate

ユーザーが`qemu-guest-agent`を導入した。VM定義にchannelがなかったため、標準`org.qemu.guest_agent.0` virtio channelをlive/persistent追加し、agent 10.0.11の疎通に成功した。channelは維持する。

- APTでstock PySide6 6.8.2.1を含む依存解決とartifact install成功
- UID 1000の`user`からoffscreen GUIを5秒起動し、timeout 124まで正常継続
- launcher/helper 0755、desktop/icon 0644、root ownership確認
- 同版reinstall成功
- `llm-manager` purge後、Gateで追加した11 dependencyだけを明示purge
- cleanup後のinstalled package集合はGate前と完全一致（added/missingとも空）
- Gate用deb、package一覧、一時HTTP serverはcleanup済み
- Debian VMはpflash NVRAMのためinternal snapshot非対応

Debian VMにはGate時点でログイン済みgraphical sessionがなく、display outputもinactiveだった。**残るGUI deb GateはDebian desktopへ通常ログインした状態でdesktop menuから起動し、実display描画を確認することだけ**。passwordを尋ねたりagent経由でpasswordを設定したりしない。再開時にユーザーがdesktopへログイン済みなら実施し、そうでなければ別sliceへ進む。

## SSH環境の注意

- Ubuntu VMのOpenSSH接続環境は後続Gate用に維持する
- hostの`/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf`が確認時にmode 0777 / `nobody:nogroup`で、通常のsystem `ssh`が`Bad owner or permissions`としてfail closedした
- Gate転送では明示`ssh -F /dev/null`とknown_hosts/keyを使用したが、これは製品経路の代替根拠にしない
- host system SSH configを無断修正しない。次のSSH production Gate前にユーザー管理下の環境問題として扱いを確認する

## 直近の検査結果

- 全534件完走（511成功・23 skip）、hostのskipは主にPySide6 runtime不在による
- Ubuntu 26.04実PySide6でQt layout、keyboard focus、close、cancel、process終了待機Gate成功
- Ubuntu 26.04/PySide6 6.10.2の実Wayland GUI起動と、Debian 13/Python 3.13.5/PySide6 6.8.2.1の通常ユーザーoffscreen起動成功
- host・Ubuntu 26.04・Debian 13のlocal user Apply計45 sampleと、hostのcomplete local診断5 sampleが成功
- GUI deb build、`packaging/verify-deb.sh`、desktop-file validation、全Phase 6 JSON parse成功
- compileall、local/remote packaging shell syntax、`git diff --check`成功

## Phase 6進捗記録（新しい順）

以下の各slice内にある「次」は記録時点の予定であり、再開時は冒頭の最新再開サマリーと末尾の作業順を優先する。

### 2026-09-05 complete local診断 slice追記（最新）

- 現在・次ともPhase 6。host system SSH configは依然 `nobody:nogroup`・0777でproduction system `ssh`がfail closed。設定は変更せずSSH再Gateを保留した。
- 固定PATH外の標準user OpenCode配置を診断とApply validationが見落とす問題を修正。`~/.opencode/bin/opencode`をowner/mode/regular file/親を含むsymlink検査後だけabsolute allowlistへ加える。任意PATH、root、SSH経路は拡張しない。
- 実稼働Ollama 0.33.2/OpenCode 1.18.25でread-only production local診断5 sampleが全`complete`。434.000–509.774 ms、CPU 3.203–4.714 ms、累積peak RSS 77,864 KiB。release SLOではない。
- `packaging/measure-complete-local-diagnosis.py`と記録 `docs/validation/phase6-complete-local-diagnosis-performance-2026-09-05.md`を追加。実設定、service、model、SSH変更なし。
- 全534 test（511成功・23 skip）、compileall、packaging shell syntax、desktop validation、JSON parse、diff check成功。両VMは `shut off`。
- 次は管理者によるhost SSH config修復後の完成GUI SSH disconnect/reconciliation、またはログイン済みDebian実display Gate。変更は未コミットで保持。

### 2026-09-05 local user Apply複数sample slice追記

- 現在・次ともPhase 6。`packaging/measure-local-user-apply.py`を追加し、production `LocalUserApplyTaskFactory`を一時rootへ限定して測定した。
- host、Ubuntu 26.04、Debian 13でcommit/rollback/recovery-requiredを各5回、全45 sample成功。AES-GCM backup、atomic Apply、validation、audit、journalと期待target stateを確認。
- artifact SHA-256 `c720bc41c0b557ad2a189255307c4976dd86f1628bce4b63ba54ec9036e61f7c`。小容量JSON、固定Gate key、注入failureのmicrobenchmarkなのでrelease SLOではない。
- Debianは製品未導入でcryptographyがなかったため正式依存3件を一時導入。測定後に全3件を明示purgeし、導入前2236 packageとのadded/missingが空で一致。
- host/guest artifactとserverをcleanupし、両VMを `shut off` へ復帰。実設定、Secret Service、systemd、SSH変更なし。詳細: `docs/validation/phase6-local-user-apply-performance-2026-09-05.md`。
- 次は完成GUI経路のSSH user Apply disconnect/reconciliation複数sample、complete診断、またはログイン済みDebian実display Gate。変更は未コミットで保持。

### 2026-09-05 cancel非協力区間の終了待機UX slice追記

- 現在・次ともPhase 6。window close後、workerを強制終了せず明示的な英日安全停止待機をstatus/accessibilityへ表示し、重複cancelとhost変更を無効化した。
- 300 ms token非確認taskで、待機中10 ms eventを10回以上処理し、worker終端後だけcloseするruntime testを追加。Ubuntu 26.04/Python 3.14.4/PySide6 6.10.2で関連31 test（30成功・1 expected skip）。artifact SHA-256 `d866b186e9936eafc08400bda7a9e7b8e009d13dfd20c3aaeda72032026e63b1`。
- host全531 test（508成功・23 skip）、compileall、packaging shell syntax、desktop validation、diff check成功。詳細: `docs/validation/phase6-close-wait-ux-2026-09-05.md`。
- package/実設定/systemd/SSH変更なし。限定artifact/serverをcleanupし、Ubuntu VMを `shut off` へ戻した。Debianは起動していない。
- 永久に戻らないin-process taskを強制終了する仕組みではない。次はcomplete/SSH/Apply性能、またはログイン済みDebian実display/menu/screen reader Gate。変更は未コミットで保持。

### 2026-09-05 対応VM＋Qt終了待機 slice追記（最新）

- 現在・次ともPhase 6。両VMを一時起動し、同一artifact SHA-256 `bb731b44ac717600d20f3c2b5c08a78c5debd23d4beeabfde1c1c22f4afb777d` をUID 1000で検証した。
- keyboard focus testの未導入QtTest依存をQtGuiのQKeyEventへ置換。Ubuntu Python 3.14.4/PySide6 6.10.2で40 test（39成功・1 expected skip）、Debian Python 3.13.5でprocess 15 test成功。
- 両VMのprocess測定は計30 sample全child回収。新規 `packaging/measure-qt-process-wait.py` は通常終了/timeout/cancel/close各3回成功。5秒継続後のcancel/close、最大event gap 10.957 ms、close→非表示最大60.346 ms、全12 child回収を確認。
- host全530 test（508成功・22 skip）、compileall、shell syntax、desktop validation、diff check成功。詳細と生データは `docs/validation/phase6-qt-process-wait-2026-09-05.md`。
- Debianはログインuserなし。実displayは未実施。package/実設定変更なし。転送・展開artifactとserverをcleanupし、両VMとも `shut off` へ戻した。
- 後続sliceで有限のcancel非協力区間の終了待機UXは完了。次はcomplete/SSH/Apply性能。ログイン済みDebianなら実display/menu Gate。5秒の合成child測定を実Agent負荷や長時間memory Gateの完了とは扱わない。変更は未コミットで保持。

### 2026-09-05 subprocess終了待機 slice追記

- 現在・次ともPhase 6。両VMはread-only確認で `shut off`。VMや実設定を変更せずhost検証を実施した。
- 両output pipeを先に閉じるchildでtimeout/cancelが無効になる不具合を2 regression testの失敗で再現し、EOF後も最大50 ms wait単位で監視するよう修正した。
- 再実行可能な `packaging/measure-process-wait.py` と測定JSONを追加。通常終了/timeout/cancel各5回、全child回収、cancel→回収4.096–48.433 ms。Qtや実Agent全体の完了根拠にはしない。
- 詳細: `docs/validation/phase6-process-wait-2026-09-05.md`。次は同一artifactの対応VM＋Qt event-loop測定、またはログイン済みDebian実display Gate。既存変更と今回変更は未コミットで保持する。
- 全530 test完走（508成功・22 skip）、compileall、packaging shell syntax、desktop validation、diff check成功。

### 2026-09-05 security/privacy slice追記

- 両VMは停止中とread-only確認したためsecurity/privacy reviewへ進んだ。VM状態は再開時に再取得する。
- 引用符付きsecretのredaction漏れを合成sentinelで再現し修正。既存GUI deb変更とともに未コミットで保持している。
- 全521 test（503成功・18 skip）、compileall、shell syntax、desktop-file-validate、diff check成功。
- 初回監査記録: `docs/validation/phase6-security-privacy-review-2026-09-05.md`。
- SEC-02を修正し、stream別の受信中上限、超過時のfail-closed回収、通常/timeout/cancelを実subprocessで検証した。Ubuntu 26.04/Python 3.14.4とDebian 13/Python 3.13.5でも同一artifactからfocused 13 test成功。検証物を削除し両VMを停止状態へ戻した。
- Apply outcomeの表示前redaction/4 KiB上限と、root helperの未使用`systemctl`出力破棄も追加した。security/privacy code review記録を更新済み。
- 利用者向け`docs/recovery-guide.md`を追加し、production route matrix、local user手動restore、`RECOVERY_REQUIRED`/`unknown`、鍵喪失、保持、upgrade/uninstall、fail-closed routeを実装とADRに合わせて記載した。
- project copyright表記、third-party notices、local/remote別CycloneDX 1.6直接依存SBOM、両debへのcopyright/notices/SBOM収録とverify Gateを追加した。Python dependencyのsource上限をdebにも反映した。
- `docs/release-checklist.md`を追加。resolved-environment SBOM、Qt package license、final lifecycle、checksum/OpenPGP署名、signed tag、公開後再検証は未完了。署名鍵は指定されておらず、自動選択しない。
- 更新後deb compositionを新しい`/tmp` copyでbuild・verifyした。local `5c286c874b979aaa680fce4778a1b37e45fd0b2d96a97d728ab1307dec79def2`、remote `d6fcbe5b7ef9639c70dc565b80d626271c462515e92b0208afd14298a3d04ab2`。両方2回build一致。remote timestamp非決定性を`SOURCE_DATE_EPOCH`で修正した。
- 全522 test（504成功・18 skip）、compileall、shell syntax、desktop validation、SBOM parse、diff check成功。詳細は`docs/validation/phase6-sbom-license-deb-composition-2026-09-05.md`。
- artifactは`dev0/UNRELEASED`でrelease候補ではない。一時build directoryはcleanupする。
- Phase 6 Qt hardeningとして、6工程のscroll、主要長文summaryの折返し、window close時のactive worker cancelと終了待機を実装した。cancelまで継続するworker中にもQt eventを20回以上処理し、協力的fake taskがcancelを0.5秒以内に観測するGateを追加した。Ubuntu 26.04実PySide6で23件（1 expected skip、1.242秒）が成功した。詳細は`docs/validation/phase6-qt-hardening-2026-09-05.md`。
- Gate artifact/serverはcleanupし、Ubuntu 26.04とDebian 13はともに`shut off`へ戻した。
- Ubuntu 26.04で実production local read-only診断の性能baselineを取得した。`partial`、25.234 ms、最大event gap 10.383 ms、process内最大RSS 67,352 KiB、worker leakなし。単一sampleかつruntime/client不在なのでrelease SLOではない。詳細は`docs/validation/phase6-production-diagnosis-performance-2026-09-05.md`。
- 実画面確認から、primary control/status/summaryのaccessible nameを内部IDではなくvisibleな英日文言へ同期した。host全527 testに加え、Ubuntu 26.04実PySide6で24件（1 expected skip、1.272秒）が成功した。
- Hosts画面でhost selectorからlanguage selectorへTab移動するkeyboard focus runtime testを追加した。追加分はhostでPySide6 skipとなるため、次回VM Gateへ束ねる。
- **次もPhase 6**。complete/SSH/Apply系production backendの複数sample、cancel/終了待機を測定する。Debian desktopがログイン済みなら実display/menu、狭幅・長文・keyboard focus・screen reader情報を確認する。

## 再開時の作業順

現在・次の作業がPhase 6であることを明示し、次の順で進める。

1. `git status --short`と未コミットdiffを確認し、Phase 6の既存変更をすべて保持する
2. VMを使う場合は現在state/IP/guest-agent疎通をread-only確認する。電源断後のIPを固定値として扱わない
3. host `/tmp/llm-manager-release-candidate-4722cfa/`のlocal/remote artifact hashを上記値と再照合し、同じcandidate setに紐付けたUbuntu local/remote・Debian local resolved-environment SBOMとQt package license reviewを進める。VMごとに開始package集合を保存し、Ubuntuは一時snapshot、Debianは追加packageの固定名によるexact cleanupを使う
4. 通常のproduction system `ssh`でUbuntuの完成GUI SSH user Apply disconnect/reconciliation Gateを行う。`-F /dev/null`を代替根拠にせず、実設定・backup・keyを使う場合は一時snapshot内のdisposable targetに限定する
5. Debian candidateの実display/menuは2026-09-10完了。最終artifactで再実行する。loginctlと実画面でsession状態を確認し、guest-get-usersの空一覧だけで保留しない
6. resolved-environment SBOM、Qt license review、実display/SSH Gate後に`debian/changelog`の`UNRELEASED`解除を判断し、最終commitから両artifactを再buildする。final lifecycle、checksum/OpenPGP署名、signed tag、公開後再検証をrelease checklistに沿って行う。署名鍵は自動選択しない
7. local root/SSH root Applyとlocal root/SSH user/root restoreは専用protocolと根拠が揃うまでfail closedを維持する。既存protocolから推測実装しない
8. 合成layout/close Gateを実display accessibility完了とは扱わず、cancelを確認しないtaskを強制終了しない

## Phase 6残件分類

- 完了: 利用者向けbackup/rollback/recovery文書、security/privacy review、直接依存SBOM/license notice、local user/SSH user Apply、local user restore、主要performance sample、長文layout、協力的workerと有限のcancel非協力区間のclose待機UX
- MVP blocker: 最終artifactのresolved-environment SBOM、全license obligationのreview、`UNRELEASED`解除後のfinal lifecycle（Debian実display/menu再実行を含む）、checksum/OpenPGP署名、signed tag、公開後再検証。release署名鍵は未指定
- acceptance/hardening: 実Agent相当の長時間負荷、実display/screen reader accessibility、通常system SSHによる完成GUI SSH切断再Gate
- Post-MVP: 複数host、自動benchmark、追加client/runtime、telemetry履歴、外部rule配布

## 安全境界

- GUI全体をrootで起動しない
- 実Ollama/OpenCode設定、既存systemd unit、SSH設定を無断変更しない
- passwordを尋ねず、argv/stdin/logへ渡さない
- venv作成、`pip install`、main workstationへのdependency installを行わない
- inventory/reconciliationをmutation authorityにしない
- 未完成routeへ既存recovery/retention/deletion helper commandを流用しない
- restore/delete/cleanupを自動実行しない
- VM lifecycle Gateは事前状態を記録し、追加したpackage/artifactだけをexact cleanupする

## 必須検査

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m compileall -q src tests setup.py
bash -n packaging/verify-deb.sh
bash -n packaging/remote/build-deb.sh packaging/remote/verify-deb.sh
desktop-file-validate packaging/desktop/io.github.nbe03xxx.llm-manager.desktop
git diff --check
```

開始時と完了時に、現在・次の作業が何Phaseか明示してください。

### 2026-09-06 root restore final consent slice追記（最新）

- 現在・次ともPhase 6。保存済みreview receiptから有効期限内のexact requestだけを渡す境界と、request SHA-256へ束縛した一回限りの最終同意session/非公開Qt dialogを追加した。
- 実行ボタンは明示チェックまで無効でdefaultにしない。結果不明時だけ単発read-only statusを許し、executeは再送しない。close中はworker終了を待ち、遅延結果を採用しない。
- host全758 test（722成功・35 expected PySide6 skip）、compileall、packaging shell syntax、desktop validation、diff check成功。詳細: `docs/validation/phase6-root-restore-final-consent-2026-09-06.md`。
- Ubuntu 26.04/Python 3.14.4/PySide6 6.10.2で同一artifact SHA-256 `67887eb7aea06a22238a1b9ff76f1f9b92b29932b5865cad6712bed564cb2b50`を検証し、Qt runtime 4件成功（全5件中inverse boundary 1 expected skip）。artifactをguest/hostから削除し、VMは事前・事後とも`shut off`。
- workspace外一時copyでfresh dev debをbuild/verifyし、新規最終同意UI moduleとexecute client、専用launcher/action/manpage/SBOMの収録を確認。SHA-256 `8b97f31d125a7b6a89dcc68fc4207732f6fffdf9e9ba6f51350275d11a26ef64`。`0.1.0~dev0/UNRELEASED`で公開候補ではない。
- package install/PolicyKit prompt/実target/service/SSHは変更していない。
- 次はinstalled PolicyKit/provisioning/OS Gateを限定実施する。それまで通常GUI route/root mutationは非公開、全変更は未コミットで保持する。

### 2026-09-06 installed root restore deny/provisioning Gate追記（最新）

- 現在・次ともPhase 6。同じ未コミットsourceから2回buildしたfresh dev debはSHA-256 `8b97f31d125a7b6a89dcc68fc4207732f6fffdf9e9ba6f51350275d11a26ef64`で一致し、verify成功。
- Ubuntu 26.04一時snapshot内へ導入。`dpkg -V`、root-owned launcher/policy/manpage、installed isolation import、review/executeの独立PolicyKit action/path/active `auth_admin`を確認した。
- inactive SSHのagentなしPolicyKitは両actionともexit 127・stdout 0 byte。installed privileged entryは不正review/requestをproduction I/O前に固定JSONで拒否した。
- installed key provisioningは`/tmp`限定root fixtureで0600 key/ready作成、安定再読込、重複拒否、自動cleanup成功。production root stateと固定Ollama targetは前後とも不在。
- artifactを削除しsnapshot revert後に旧`0.1.0~dev0-1`、target/state/artifact不在を確認。VMを`shut off`へ戻し一時snapshotも削除。詳細: `docs/validation/phase6-root-restore-installed-deny-provisioning-2026-09-06.md`。
- 次はvalid requestのdisposable OS mutation/service Gate、その後active desktop PolicyKit認証を実施する。通常GUI routeは非公開、全変更は未コミットで保持する。

### 2026-09-06 valid local root restore OS Gate追記（最新）

- 現在・次ともPhase 6。Ubuntu 26.04一時snapshotで、installed key/origin capture、AES-GCM evidence、trusted review、valid canonical requestから専用execute entryを一度だけ実行した。
- current `deb90d067dcd9436cd5a4e48eb0c88ff65e84b7fae81c985d1f01864bf9de3aa`からoriginal `82ff1fcf582006def7fdf45c42f243961f75f1ba685247a870d48077db13204c`へ固定targetを復元。実systemd reload/restart、127.0.0.1 version/tags API、root 0600 review/attempt/result、strict audit開始/終了、read-only committed statusを確認した。
- 同じrequestのreplayは`root_restore_request_already_used`で拒否され、target/resultは不変。fresh debは3回目もSHA-256 `8b97f31d125a7b6a89dcc68fc4207732f6fffdf9e9ba6f51350275d11a26ef64`で一致しbuild内758 test/verify成功。
- artifact削除後にsnapshot revertし、旧`0.1.0~dev0-1`、Ollama/Gate unit、target、root state、11434 listener、artifactの不在を確認。VMを`shut off`へ戻し一時snapshotを削除。詳細: `docs/validation/phase6-root-restore-valid-os-gate-2026-09-06.md`。
- QEMU guest agentでinstalled entryを直接実行したためactive desktop interactive PolicyKit認証は残件。次は認証prompt/最終route公開review。通常GUI routeは非公開、全変更は未コミットで保持する。
