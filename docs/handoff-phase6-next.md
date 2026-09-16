# 次チャット用引継ぎ（2026-09-14）

`/home/yoshimi/WorkSpace/LLM-Manager` のPhase 6 Hardening / MVP Releaseを続けてください。
まず本ファイルを読み、必要な詳細だけ `docs/handoff-phase6.md` と検証記録で補ってください。
本ファイルを過去の時系列記録より優先してください。

## 今回の継続結果（最優先）

- 2026-09-16、final source commit `5b7d4de03e495fe630deab952de043f945a22bd7`から
  tracked sourceを独立2回展開し、local／remote両debを各2回build。各artifact、buildinfo、
  changesがbyte一致。local SHA-256 `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1`、
  remote SHA-256 `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4`。
  各build内806 test、4 verifier、tracked source一致、package展開binary／owner／mode／同梱境界監査が成功。
  artifactは`/tmp/llm-manager-final-5b7d4de-20260916/artifacts/`へ保持。未署名・未公開。
  Reproducible build 7項目とfinal binary監査が完了し、進捗29/44、65.9%。
- 2026-09-16、確定済みrelease判断に基づきfinal source metadata transitionを開始。
  `debian/changelog`を`unstable`へ変更し、release日時を2026-09-16、署名者を
  `NBE03xxx <NBE03247@nifty.com>`へ固定。release notesから`TBD`を除去し、signed tagを
  `v0.1.0`、source archiveを`llm-manager-0.1.0.tar.gz`、artifact identityの正本を
  `SHA256SUMS`とした。最終artifact、署名、tag、公開は未実施。進捗21/44、47.7%。
- 2026-09-15、[通常GUI SSH自然runtime障害rollback](validation/phase6-natural-runtime-rollback-2026-09-15.md)が成功。通常GUIで診断→Agent推奨2件→review→承認→Apply、利用者がREMOTE sudo認証。Apply直後だけ実OpenCode 1.18.25 binaryを一時退避し、production validator自身が`not_installed`を検出。validation結果注入なし、Apply/rollback各1回、`rolled_back`、configとbinary hash/mode/version復元、journal/dual backup/GUI一致。継承harnessが専用referenceをcleanupする一方productionは`local-master-v1`を作る不整合を検出し、開始時不在・今回時刻/属性一致の1件だけ秘密値を読まず削除、scriptを修正。両VM baseline/session完全一致、snapshot削除、時計補正、checksum成功。最終artifact反復が残るため進捗19/44、43.2%は維持。
- 2026-09-15、利用者が[release専用OpenPGP鍵](validation/phase6-release-signing-key-2026-09-15.md)を作成し試験署名を検証。主鍵`353F4D4F55175F537FBCD07C3E2532969B404FFD`（Ed25519 certification、2031-09-14まで）、署名副鍵`034DA1601E14BE534254BA4DD8F253C086BE34C2`（Ed25519 signing、2027-09-15まで）。保管責任者は`Project owner (NBE03xxx)`、後継者なし、活動中だけ1年更新。公開鍵のみ`RELEASE_KEY.asc`へ収録し、秘密file名を`.gitignore`へ追加。target distributionは`unstable`、公開先GitHub Releases、Maintainer/changelog signerは`NBE03xxx <NBE03247@nifty.com>`と決定。実署名/tag/公開は未実施。進捗19/44、43.2%。
- 2026-09-15、[release transition readiness audit](validation/phase6-release-transition-readiness-2026-09-15.md)を実施。`HEAD`/`origin/main`は`c86f04d`、採用pre-final candidate hashも再一致。GitHub repositoryはpublic、既存tag/Releaseは0件。[0.1.0 release notes draft](release-notes-0.1.0-draft.md)へ必須sectionと検証手順を準備した。target distribution、changelog署名者表記、release専用OpenPGP fingerprint／保管責任者、公開先・公開承認が未確定のため`UNRELEASED`を維持する。判断後の順序をmetadata確定→final commit→再現build→SBOM/binary監査→OS/GUI/security Gate→checksum/署名→tag/公開後再検証と固定。進捗18/44、40.9%は変更なし。
- 2026-09-15、commit `7f846f5`から[認証UI改善candidate](validation/phase6-auth-context-candidate-build-2026-09-15.md)をlocal/remote各2回buildしbyte一致。local SHA-256 `ecc099a6ae285d99fe1990cc1335dbff10f17019a766d8527566819f850eba9a`、remote `4ca5e152c2738c1fa2ca92eaf5ab4802ecfd88438f15f54780117f463b9edbb2`。各build内806 testと両verifier、package展開監査成功。
- [installed UI Gate](validation/phase6-auth-context-ui-installed-2026-09-15.md)でDebian通常desktopに`REMOTE sudo — phase6-auth-context-ui`とPolicyKitの`LOCAL authentication` messageを表示し、AT-SPI/画面保存。通常GUI SSH Applyは1回、committed、validation 2件passed、注入なし。localはread-only review actionを利用者がキャンセルしprocess不在。
- 前日performance Gateが作成した`local-master-v1` 1件をcleanup harnessのreference置換ずれで見逃していたことを作成時刻から特定。対応backup/state不在と非秘密propertyを照合して正確な1件だけ削除し、旧記録を訂正した。本Gate専用key/path/packageも削除、両VM baseline完全一致、snapshot削除、時計補正、checksum成功。進捗18/44、40.9%、0.1.0 / UNRELEASEDを維持。

- 2026-09-14、[認証コンテキストUI改善](validation/phase6-authentication-context-ui-2026-09-14.md)を実装。remote SSH loginは`REMOTE SSH login — <user@host/alias>`、remote sudoは`REMOTE sudo — <alias>`を外部ターミナルタイトルへ表示し、local Apply/root restoreのPolicyKit description/messageには`LOCAL`を明記した。認証の固定argv、helper protocol、秘密情報非保持は不変。
- 対象38件と全806件（767成功・39 expected skip）、compile/XML/shell/desktop/SBOM/diff検査が成功。従来の`ff7913b` candidateは本改善を含まないため、新sourceからのcandidate再buildとDebian通常desktop目視Gateを残す。final artifactと進捗18/44、40.9%は未変更。

- 2026-09-14、[通常GUI SSH Apply 5 sample performance Gate](validation/phase6-ssh-apply-performance-2026-09-14.md)が成功。Debian通常user・installed candidate・通常`qt_app.main`で、各sampleを診断→Agent推奨2件→review→承認→Applyまで操作。5/5 committed、Apply各1回、validation 2件passed、開始hashと終了config一致。plan/approval/transport/validation注入なし。
- Applyクリック→完了（対話sudo込み）は13,222.943〜32,539.075 ms、中央値15,416.516 ms。`ssh.user_apply.invoke`は214.865〜252.493 ms、中央値231.750 ms。sample間のfixture resetは終了回収後・次の測定前に限定。observerのsample-01重複画面保存は測定・製品state非影響として記録し、sample-02以降修正。
- 証拠checksum成功。専用key/alias/state/packageを削除し両VM baseline完全一致、一時snapshot削除済み。snapshot復元後のUbuntu約1,158秒遅れはNTP設定を変えずsystem clockのみ補正し、VM間差0.023秒。性能の複数sampleは補完したが、自然障害rollback・最終artifact Gateが残るため進捗18/44、40.9%を維持。

- 2026-09-14、[pre-final security regression](validation/phase6-pre-final-security-regression-2026-09-14.md)が成功。現`main`でproduct source/test/packaging/version surfaceは採用source `ff7913b`から不変。focused 159件（158成功・1 expected skip）、全806件（767成功・39 expected skip）、両candidate deb verifier、compileall・shell・desktop・SBOM JSON・`git diff --check`が成功した。保存済みVM operationは再実行していない。
- `UNRELEASED` candidateであり最終artifact反復ではないため、security最終commit項目は未完了、進捗18/44、40.9%を維持。次は実SSH Apply性能の複数sample、自然障害rollback、または最終artifact開始に必要なdistribution/signing key判断を進める。署名・tag・公開は未実施。

- 2026-09-14、[local root manual restore通常GUI＋PolicyKit Gate](validation/phase6-local-root-restore-gui-2026-09-14.md)が成功。Debian通常user・installed candidate・通常`qt_app.main`でroot backup inventory→選択→review→保存→final consent→restoreを操作し、active desktopの実PolicyKit promptで認証した。review/attempt/result各1件、strict audit 2件、`committed`、開始hash・root/root 0644復元、systemd restart/API validationを確認。
- 期限切れでunconfirmedになった先行review saveは同一要求を再送せず、root stateにreview/attempt/result/auditがないことをread-only確認して新規reviewを作成した。restore要求は1回だけ。専用root key/state/unit/target/pathと追加12 packageを削除し、Debian baseline/session完全一致、snapshot削除済み。回帰806件（767成功・39 expected skip）、証拠checksum、`git diff --check`成功。
- 2026-09-14、[local user manual restore通常GUI Gate](validation/phase6-local-user-restore-gui-2026-09-14.md)が成功。Debian通常user・installed candidate・通常`qt_app.main`で、Local診断→Agent推奨2件→review→承認→Apply→実AES-256-GCM backupを作成。同じGUIで明示Refresh→backup選択→preview→正確な同意→Run Restore→再Refreshを操作した。Apply/restore各1回、restore evidenceは`committed`、初期config hashへ復元、inventory表示も一致。
- observerは画面/state保存だけでplan/approval/GUI stateを注入していない。Secret Service、manifest、journal、restore attempt/result、audit 5-event hash chainの結合を機械照合。専用key/state/pathと追加12 packageを削除し、Debian baseline/session完全一致、external snapshot削除済み。回帰806件（767成功・39 expected skip）と証拠checksum、`git diff --check`成功。
- 現`UNRELEASED` candidate各1 sampleのため進捗18/44、40.9%を維持。local user/root manual restoreの通常GUI Gateは分離して完了。次は性能の残条件・複数sample、自然障害rollback、またはfinal artifact条件を進める。保存済みoperationを再実行しない。version 0.1.0 / UNRELEASED、署名・tag・公開未実施を維持する。

- 2026-09-14、通常GUI全経路のSSH自動rollbackが成功。診断→Agent推奨2件→
  review→承認→Applyは注入なし。production validation 2件passed保存後、対象fileを
  変えないGate failure 1件で分岐し、Apply/rollback各1回、rolled_back、開始hash復元。
  GUI表示はobserver JSONと画像で確認。詳細:
  `docs/validation/phase6-full-gui-rollback-2026-09-14.md`。
- journal/rollback request/local AES-GCM manifest/remote verified receiptを照合。
  両VM baseline完全一致、専用state/package/snapshot削除、復元後時計補正済み。
  validation faultを含む現candidate 1 sampleなので進捗18/44、40.9%を維持。
- 次はlocal user/root manual restoreの全GUI操作、性能複数sample、または公開前の
  final artifact Gateへ進む。version 0.1.0 / UNRELEASEDと署名未実施を維持する。

- 2026-09-14、通常GUI全経路＋実NIC断のSSH Apply照合が成功。
  診断→Agent推奨2件→review→承認→Applyは注入なし。Apply 1回、NIC down 4.023秒、
  実SSH exit 255、復旧後result照合でcommitted。config/journal/dual backup/GUI一致。
  詳細: `docs/validation/phase6-full-gui-network-2026-09-14.md`。
- `/tmp`消失後にff7913b tracked sourceからcandidateを再buildし、両debが採用hashと一致。
  build内806 test、両verifier成功。OpenCode 1.18.25も公式hash一致で再取得した。
- 両VM baseline完全一致、試験専用state/key/alias/package削除、一時snapshot削除、
  時計補正済み。実行中watcher/GUI/relayなし。進捗18/44、40.9%を維持。
- 後続で通常GUI rollback全経路も完了。残りは性能の複数sample、
  local user/root restore全GUI操作、final artifact Gate。公開用署名はまだ行わない。

- 通常GUI経路のSSH Applyが成功。full-gui-sshでOpenCode 1.18.25、Agent推奨2件を
  利用者が選択・レビュー・承認し、compaction.auto/prune=trueへcommitted。
  plan/approval/transport注入なし、通常qt_app.main＋観測subclass、20画面履歴保存。
  詳細: `docs/validation/phase6-full-gui-ssh-2026-09-13.md`。
  両VM baseline完全一致、試験データと一時snapshot削除、時計補正済み。
  GUI/認証待ち/監視processは残していない。回帰806件（767成功・39 skip）と
  証拠checksum・journal/manifest/receipt対応検査も成功。2026-09-14に記録保存を再開。
- Orca保存WAVの製品名・Hostsの発音/順序/聞き取りやすさについて、利用者が
  「問題なく聞き取れた」と回答。今回captureの人による聴取確認は完了。
- 次は通常GUIとrollback/通信断の組合せ、local restore全操作などの残条件。
  未診断Recommendationsが説明なく空欄になるUI改善候補も観測された。

- network-rollback2でrollback応答中の実NIC切断・結果照合が成功。NIC down 4.055358秒、
  実SSH exit 255、Apply/rollback各1回、復旧後result読み取り1回でrolled_back。
  正常Apply後にもresultを1回読む。fixture hashとGUI表示を確認済み。
- 先行network-rollbackはhelper exit 1、recovery_required、NIC未切断の非採用試行。
  時計ずれが有力だが失敗時のhelperエラーコード未採取のため原因未確定。
  次試行でprepare後のUbuntu約1.72秒遅れを測定し、同期後に成功した。
- 両試行のcleanup完了、両VM baseline完全一致、一時snapshot削除、時計補正済み。
  実行中watcher・GUI・relayは残していない。製品source ff7913bを維持。
- 詳細: `docs/validation/phase6-cross-vm-network-rollback-2026-09-13.md`。
  回帰806件（767成功・39 expected skip）、証拠checksum67件・構文・空白検査成功。
  次はOrca WAVの人による聴取と通常GUI全操作などの残条件整理。
  以下の中断点・次候補は継続前の履歴として参照する。

## 前回の中断点（履歴）

- ユーザーが5時間枠の残量7%と報告し、ここで中断・新しいチャットへの引継ぎ保存を依頼。
  使用量リセット、監視、自動再開、新規チャット作成は依頼されていない。実施しない。
- 最終検証commitは `e098d11`（`main`、originへpush済み）。本引継ぎ編集開始時はworktree clean。
  本引継ぎの保存はその後の文書更新として扱う。
- 最後の成果はnet2の実NIC断commit照合。Apply 1回、NIC down 4.020秒、実SSH exit 255、
  復旧後result読み取り1回でcommitted。両VMのcleanupと時計補正まで完了した。
- 次の実装・検証候補は **rollback応答中の実NIC切断と結果照合**。
  net2はuser-apply専用のrelay/observerであり、そのままrollbackへ流用すると誤検証になる。
  新しいnamespace、snapshot、operation、証拠directoryで設計・検証する。
- 監視のreadyを確認してからGUIをlaunchする。利用者がRun Applyを押し、Debian画面の
  外部端末でUbuntuユーザーのsudo認証をする。開始時点で入力可能か確認する。
- 実行中の監視・Gate・回収待ちprocess・一時snapshotは残していない。
  再開時はread-onlyで状態を確認し、過去のprepare/launch/watchを無条件に再実行しない。
- 最終回帰806件（767成功・39 expected skip）、証拠checksum、Git空白検査成功。
  version 0.1.0 / UNRELEASED、製品source ff7913bを維持。公開承認や署名鍵は未確定。

## 現在位置とGit

- Phase 0〜5完了。現在・次ともPhase 6。version 0.1.0、distribution `unstable`。
  最終Gate、署名、signed tag、公開後再検証が完了するまで一般配布しない。
- branch `main`。最新commit/remote/worktree状態は再開時に取得する。
- 本文書更新は別commitになるため、再開時は `git status -sb` と `git log -5 --oneline` を取得する。
- ユーザーは「検査後にまとめてコミット・プッシュ」を承認済み。各検証sliceをその方針で保存してきた。
- `ff7913b`以降は検証script・証拠・文書のみ変更。製品source変更なし。
- 実行中Gate、認証待ち、未復元snapshotはない。local user/root manual restoreの通常GUI Gateとnet2の実NIC断commit照合に成功。
  net/net2とr2/r3はすべて両VM cleanup完了。最後にsystem clockを補正済み。
  初回netは監視前にApplyが完了し、stale markerチェックによりNIC切断を中止。
  非採用証拠を保存して両VM cleanup済み。net2は新しいoperationであり再送ではない。
  r2は時計ずれの拒否を再現、時計補正後の新規r3でrollback成功。
  snapshot復元後も両VMの時計を明示承認に基づき補正済み。NTP設定は未変更。
  以前のcross-vm Gateと60分試験もcleanup済み。

## 進捗の表示方針

ユーザーは今後の報告に進捗率の%表示を希望している。
再開時にrelease checklistのトップレベルcheckboxを集計し、分母を明記する。
2026-09-16現在は29/44件、**65.9%（公開チェックリスト項目数ベース）**。
Phase 0〜5を含む全開発工数の割合や残り時間を意味しない。
以前報告した「技術検証約89%／公開準備約62%」は重み付けを定義していない概算であり、
この65.9%とは比較しない。今後は再集計可能な値を主表示とする。
部分検証が増えてもcheckboxの完了条件を満たさない限り数値は上げない。

## 採用candidate

### Final artifact（2026-09-16）

source commit: `5b7d4de03e495fe630deab952de043f945a22bd7`

保存先: `/tmp/llm-manager-final-5b7d4de-20260916/artifacts/`

| artifact | SHA-256 |
| --- | --- |
| `llm-manager_0.1.0_all.deb` | `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1` |
| `llm-manager-remote-helper_0.1.0_all.deb` | `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4` |
| `llm-manager-0.1.0.tar.gz` | `6d569199110bdc155a14c0a6222353ccc92380b63b20cfebff083ace1c91fe18` |

独立2回build、各build内806 test、両runのverifier、展開監査に成功。最終OS／GUI／security Gate、
resolved-environment SBOM、`SHA256SUMS`、署名、tag、公開は未実施。下記pre-final candidateを混用しない。

### Pre-final candidate（履歴）

source commit: `7f846f5fb1134be7df06490f30a5216ab414ae0d`

保存先: `/tmp/llm-manager-candidate-7f846f5-20260915/`

| artifact | SHA-256 |
| --- | --- |
| `llm-manager_0.1.0_all.deb` | `ecc099a6ae285d99fe1990cc1335dbff10f17019a766d8527566819f850eba9a` |
| `llm-manager-remote-helper_0.1.0_all.deb` | `4ca5e152c2738c1fa2ca92eaf5ab4802ecfd88438f15f54780117f463b9edbb2` |

引継ぎ更新時に両hashを再確認済み。再開時も存在/hashを確認する。
tracked sourceから両debを独立2回build/verifyしbyte完全一致。
各local build内806 test（767成功・39 expected skip）、ELF/shared library/bytecode混入なし。
認証表示のinstalled UI Gateは完了。旧ff7913b/b15a984/4722cfaセットは過去証拠用。
新candidateの他Gateへ旧artifactのbyte identityを混用しない。
詳細: `docs/validation/phase6-auth-context-candidate-build-2026-09-15.md`。

## 完了済み

1. **Ubuntu local/remote lifecycle**: 新candidate両debのupgrade/reinstall/remove/fresh/purge成功。
   local UID1000 isolated importとoffscreen Qt起動/close、remote metadata/owner/mode/private
   runtime/local GUI非混入を確認。各snapshot復元後baseline完全一致、一時snapshot削除済み。
   記録: `docs/validation/phase6-ff7913b-ubuntu-lifecycle-2026-09-13.md`。
2. **Debian lifecycle/AT-SPI**: 新candidateのfresh/reinstall/remove/再fresh/purge、英日Wayland
   installed launcher起動、用途/label relation/focusable/内部ID非露出、Alt+F4 exit 0成功。
   追加12件のみpurgeしbaseline完全一致、deb削除。このlifecycle sliceでは旧版upgrade、menu再操作、
   Orca音声を未実施だったが、後続の上記9〜11で検証・captureし、人のWAV聴取も完了。
   記録: `docs/validation/phase6-ff7913b-debian-2026-09-13.md`。
3. **Ubuntu accessibility**: combo box用途欠落・内部ID露出を修正し英日AT-SPI成功。
   system PySide6 focused 38件（37成功・1 expected skip）。
   記録: `docs/validation/phase6-accessibility-atspi-2026-09-12.md`。
4. **60分Agent Gate**: 3600.116秒、全15 check成功。最大event gap 66.258 ms、cancel回収
   53.625 ms、親RSS増加3,028 KiB。child reap、worker inactive、watchdog不使用。
   合成Agent相当workload。モデル推論/network APIは含まない。4時間soakは任意。
   記録: `docs/validation/phase6-long-running-agent-2026-09-13.md`。
5. **Ubuntu local環境SBOM**: 新candidate installed環境1907 packageを採取。artifact hash、
   内外checksum、TSV/inventory/BOM整合性成功。copyright欠落は既存Brave関連2件。
   collector exit 2、license review完了判定false。snapshot復元後baseline完全一致。
   記録: `docs/validation/phase6-ff7913b-ubuntu-local-sbom-2026-09-13.md`。
6. **Ubuntu remote helper環境SBOM**: 新candidateをfresh installし1908 packageを採取。
   APT追加はhelper 1件のみ。artifact hash、内外checksum、TSV/inventory/BOM整合性成功。
   copyright欠落は既存Brave関連2件、collector exit 2、license review完了判定false。
   snapshot復元後baseline完全一致、一時snapshot削除済み。
   記録: `docs/validation/phase6-ff7913b-ubuntu-remote-sbom-2026-09-13.md`。
7. **Debian local環境SBOM**: 今回のAPT simulationでcandidate＋新規依存11件を固定し、
   fresh install環境2248 packageを採取。copyright欠落なし、collector exit 0。
   artifact hash、内外checksum、TSV/inventory/BOM整合性成功。12件だけを明示purgeし、
   baseline完全一致、audit/check成功。VMとWayland sessionはrunning/activeを維持。
   記録: `docs/validation/phase6-ff7913b-debian-local-sbom-2026-09-13.md`。
8. **Qt/PySide6 license review**: 3環境の現archiveから各25 binary・6 source系統を比較。
   選択packageのcopyright欠落なし。Ubuntu local/remoteのmetadata/原文hash一致、両OSの
   PySide6主Files節とQt GPL Exception本文、QtBase主Files節、追加license名を確認。
   直接依存SBOMは主選択肢の要約として整合。法的適合の自動完了とは扱わない。
   記録: `docs/validation/phase6-ff7913b-qt-license-review-2026-09-13.md`。
9. **Debian旧版upgrade**: commit 8854232のtracked sourceからbuild・historical verifier済みの
   `0.1.0~dev0`をfresh installし、新candidate `0.1.0`へupgrade。simulation/実行とも変更は
   `llm-manager` 1件だけ。dpkg検証、UID1000 isolated import/offscreen Qt成功。
   固定12件だけをpurgeしbaseline完全一致、Wayland sessionを維持。
   記録: `docs/validation/phase6-ff7913b-debian-upgrade-2026-09-13.md`。
10. **Debian menu再検査**: GNOME overviewで`llm`検索し、icon/名称を画像確認。Enterで
    日本語UIを起動し、UID1000と固定argv、Alt+F4通常終了を確認。固定12件だけをpurgeし
    baseline/session完全一致、VM running。画像を含むmanifest全件一致。
    記録: `docs/validation/phase6-ff7913b-debian-menu-2026-09-13.md`。
11. **Debian Orca音声capture**: 一時prefsでOrcaを起動し、製品名、Hosts用途/valueを含む
    12発話eventと20.672秒の非無音WAVを保存。app exit 0、toolkit accessibility false復元、
    固定12件purge後baseline/session完全一致。人によるWAV聴取確認も完了。
    記録: `docs/validation/phase6-ff7913b-debian-orca-2026-09-13.md`。
12. **別VM間SSH正常Apply（部分Gate）**: ff7913b Debian GUI→Ubuntu remote helperで
    実OpenCode/dual backup/commit、応答喪失例外注入後のimmutable result照合成功。
    Apply 1回、Results可視。rollback予定caseはsudo認証待ちでApply前に停止し未検証。
    再送なし、設定hash維持、両VM復元済み。
    記録: `docs/validation/phase6-cross-vm-ssh-2026-09-13.md`。
13. **別VM間SSH rollback（部分Gate）**: r2でsudo認証後の時刻ずれ拒否を特定。
    両VM時計を補正した新規r3で、不正JSON→自動rollback成功。
    Apply/rollback各1回、例外注入後のimmutable result照合、元hashとResults表示を確認。
    両VMのpackage/manual/保全path/session復元済み。
    記録: `docs/validation/phase6-cross-vm-rollback-2026-09-13.md`。
14. **実NIC断後のSSH commit照合（部分Gate）**: net2でhelper成功後のstdoutを
    試験relayで保留し、Ubuntu live NICを4.020秒切断。SSH自身がexit 255、
    復旧後のimmutable result読み取り1回でcommitted。Apply 1回、例外注入なし。
    両VM復元済み。記録: `docs/validation/phase6-cross-vm-network-2026-09-13.md`。
15. **local user manual restore通常GUI Gate**: Debian通常user・installed ff7913b candidate・
    通常`qt_app.main`でLocal診断からApply/暗号化backupを作成し、同じGUIで明示Refresh、preview、
    exact consent、restore、再Refreshを操作。Apply/restore各1回、committed、開始hash復元、
    Secret Service/manifest/journal/execution/audit結合、baseline cleanupを確認。
    記録: `docs/validation/phase6-local-user-restore-gui-2026-09-14.md`。
16. **local root manual restore通常GUI＋PolicyKit Gate**: Debian通常user・installed candidate・
    通常`qt_app.main`でroot backup inventoryからfinal restoreまで操作。active desktopの実PolicyKit、
    review/attempt/result各1件、strict audit、committed、固定target開始hash、systemd/API、完全cleanupを確認。
    unconfirmedの先行review要求は再送せず、新しいreviewだけを実行へ使用した。
    記録: `docs/validation/phase6-local-root-restore-gui-2026-09-14.md`。

旧candidateの実OpenCode/dual backup/SSH GUI Apply・rollback・応答喪失後照合も成功済みだが、
loopback SSH・Gate plan/例外注入を含み、別マシン間の物理切断ではない。
通常SSH診断5 sampleと実SSH待機cancel3 sampleも限定baselineとして保持する。
2026-09-13にはhost→Ubuntuの仮想NICを実際にdownにした状態でキャンセルを検証。
回収32.031 ms、link up復元、新しいstrict SSH接続とremote有限process不在を確認した。
詳細: `docs/validation/phase6-ssh-link-cut-2026-09-13.md`。Qt/Apply完了の代替ではない。

## 次の作業（この順を基本とする）

1. local user/root manual restoreの全GUI操作、性能の複数sample、自然runtime障害rollbackは現candidateで完了。次はfinal artifact Gateを進める。
2. `docs/release-checklist.md` のSSH機能/別マシン間切断、最終artifactのSBOM/lifecycle等を
   継続する。
   利用者はDebian画面でUbuntuのsudo認証が可能と回答済み。
   Debian GUI→Ubuntu SSHの正常Applyとrollbackは別caseで成功済み。
   実NIC断後の正常Apply照合はnet2、rollback照合はnetwork-rollback2で成功済み。次は
   通常GUIのcommit/rollback全経路も現candidateで成功済み。最終artifact項目は未完了のまま。
   net2は成功応答を10秒保留するrelayと短いSSH keepaliveの限定caseである。
   次回ネットワークGateは必ずGUI launchより先にwatch readyを確認する。
   snapshot操作後は両VM時計を確認すること。r2で約200秒先のrequestを拒否した。
   手動Run Applyで入力タイミングを合わせる。保存済みoperationは再送しない。
3. release専用署名鍵、target distribution、署名者、公開先は確定済み。final source metadataで
   `UNRELEASED`を`unstable`へ変更し、release日時・変更点も確定済み。
   秘密鍵を自動生成・推測選択しない。
   release署名・tag・公開の承認を、通常のcommit/push承認と同一視しない。

## VMと復元条件

- 最後の確認ではUbuntu `ubuntu26.04`、Debian `debian13` ともrunning。電源状態を維持する。
- Ubuntu user `yoshimi` UID1000、最後のIP `192.168.122.48`、Wayland session 3。
- Debian user `user` UID1000、Wayland session 2。現在IP/session/lock状態は再取得する。
- Ubuntu既存snapshot `phase4-pre-local-deb-20260831` は保持。一時Phase 6 snapshotは削除済み。
- package/manual/保全pathは各Gate開始値へ復元済み。ホストのcandidate・一時build treeは保持。
- `guest-get-users`空だけでログイン不在と判定しない。loginctl/Wayland状態を確認する。
- 通常system SSHは復旧確認済み。sandbox内owner表示だけを根拠に修復を要求しない。
  sandbox拒否時は正式に権限昇格し、`-F /dev/null`で迂回しない。

## 再利用できる入口

- `docs/validation/phase6-local-root-restore-gui-2026-09-14.md`：通常GUI＋実PolicyKitのlocal root restore結果。
- `docs/validation/local-root-restore-gui-2026-09-14.py`、同名directory：one-shot入口と全証拠。完了済みoperationを再実行しない。
- `docs/validation/phase6-local-user-restore-gui-2026-09-14.md`：通常GUI全経路のlocal user Apply/manual restore。
- `docs/validation/local-user-restore-gui-2026-09-14.py`、同名directory：完了済みGate入口と全証拠。再実行しない。
- `docs/validation/phase6-full-gui-rollback-2026-09-14.md`：通常GUI全経路のSSH自動rollback。
- `docs/validation/full-gui-rollback-2026-09-14.py`、同名directory：入口と全証拠。
- `docs/validation/phase6-cross-vm-network-2026-09-13.md`：最新の実NIC断commit照合と試験の境界。
- `docs/validation/cross-vm-network-2026-09-13.py`：基礎操作script。初回netは古い通知で切断中止。
- `docs/validation/cross-vm-network2-2026-09-13.py`、同名directory：採用net2の入口と全証拠。
- `docs/validation/phase6-cross-vm-rollback-2026-09-13.md`：r3の別VM間rollback成功（例外注入）。
- `docs/validation/cross-vm-rollback-r2-2026-09-13.py`、`cross-vm-rollback-r3-2026-09-13.py`：旧Gate構成。
- `docs/validation/phase6-cross-vm-clock-rejection-2026-09-13.md`：時計ずれの拒否再現。
- `docs/validation/sync-gate-vm-clocks-2026-09-13.py`、同名JSON：承認済み時計補正の方法・記録。
  両VMのhwclock不在を検査しsystem clockのみ補正。NTP設定は変更しない。
- `/tmp/phase6-cross-vm-opencode-1.18.30.tar.gz`：保持した公式OpenCode archive。
  再使用前にSHA-256 `60c92147d0d86ca606dda8a77260d3c87e0ef959eb2d8dbffb34df6d8a64e063` を照合する。
- `docs/validation/collect-ff7913b-ubuntu-sbom-2026-09-13.py`：今回のUbuntu local SBOM採取。
- `docs/validation/sbom-ff7913b-ubuntu-local-2026-09-13/`：archive/verifier/APT/baseline/restored。
- `docs/validation/collect-ff7913b-ubuntu-remote-sbom-2026-09-13.py`：今回のUbuntu remote SBOM採取。
- `docs/validation/sbom-ff7913b-ubuntu-remote-2026-09-13/`：remote archive/verifier/APT/baseline/restored。
- `docs/validation/collect-ff7913b-debian-sbom-2026-09-13.py`：今回のDebian local SBOM採取/cleanup。
- `docs/validation/sbom-ff7913b-debian-local-2026-09-13/`：Debian archive/verifier/APT/baseline/cleaned。
- `docs/validation/review-ff7913b-qt-licenses-2026-09-13.py`：現archiveのQt/PySide6比較。
- `docs/validation/qt-license-review-ff7913b-2026-09-13.json`：package/source/license/hash結果。
- `docs/validation/debian-upgrade-ff7913b-2026-09-13.py`：Debian旧版upgrade/cleanup Gate。
- `docs/validation/debian-upgrade-ff7913b-2026-09-13/`：upgrade simulation/log/inventory/cleanup。
- `docs/validation/debian-menu-ff7913b-2026-09-13.py`：Debian menu導入/process/cleanup Gate。
- `docs/validation/debian-menu-ff7913b-2026-09-13/`：menu画像/process/APT/inventory/cleanup。
- `docs/validation/debian-orca-ff7913b-2026-09-13.py`：Orca/PipeWire captureとcleanup Gate。
- `docs/validation/debian-orca-ff7913b-2026-09-13/`：WAV/debug/発話/画像/APT/inventory。
- `packaging/collect-installed-sbom.py`、`packaging/verify-environment-evidence.py`：採取・archive検証。
- `docs/validation/phase6-0.1.0-candidate-environment-sbom-qt-2026-09-09.md`：旧候補のQt原文review参考。
- `docs/validation/lifecycle-ff7913b-2026-09-13.py`：Ubuntu local/remote lifecycle。
- `docs/validation/debian-ff7913b-2026-09-13.py`：Debian lifecycle/英日AT-SPI。
- `docs/validation/ssh-gui-2026-09-11/vm-lifecycle.py`：QGA実行/転送共通関数。
- `docs/validation/phase6-ssh-gui-installed-2026-09-11.md`：旧候補の限定SSH GUI証拠。

証拠scriptは固定path/hashと実行時stateを含む。新規Gateは別script/outputへ作成する。
QEMU guest-execの完了結果は一度読むと消費されるため、最初の完了pollで保存する。
GUI全体をrootで起動しない。SSH mutationを自動再送しない。利用者の秘密情報を要求しない。
sub-agentは明示依頼がないため起動しない。
