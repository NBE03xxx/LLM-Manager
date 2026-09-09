# MVP Release Checklist

このchecklistは、同じGit commitから作成したlocal deb、remote helper deb、SBOM、checksum、署名を1つのrelease setとして判定する。versionは`0.1.0`へ固定済みだが、`UNRELEASED`のまま一般配布しない。

## 1. Scopeとversion freeze

- [x] MVP production routeをlocal user/SSH user Applyとlocal user/local root manual restoreに固定した。local root Applyはactionable Ollama rule待ち、SSH root ApplyとSSH user/root restoreは専用protocol待ちとしてrelease scopeから外し、requirements、MVP scope、README、route availability、受け入れ条件を照合した。
- [ ] Debian 13 desktopへ通常ログインし、desktop menuからlocal debの実display起動を確認する。
- [ ] performance、長時間Agent、accessibility、完成GUI経路のSSH切断Gateを判定する。長文layout、window close時のcancel・worker終了待機、協力的fake taskと有限のcancel非協力区間のevent処理・明示的待機UXはUbuntu 26.04実Qtの合成Gateまで完了した。local user production Apply compositionはhost/Ubuntu/Debianでcommit/rollback/recovery-requiredを各5 sample、実Ollama/OpenCodeのcomplete local診断はhostで5 sample完了。SSH Applyと実displayは未完了。
  - Ubuntu 26.04のproduction local read-only診断で単一sample基準値を取得済み。`partial`、25.234 ms、最大event gap 10.383 ms、最大RSS 67,352 KiB。complete/SSH/Apply系の複数sampleとhardware基準は未完了。
- [x] release versionを`0.1.0`に固定し、`pyproject.toml`、`debian/changelog`、remote `control`、両helper metadata、SBOM、verifier、production helper compatibility allowlistを一致させた。`UNRELEASED`の解除は最終Gate後の別項目とする。
  - `DebianPackagingTests.test_release_version_surfaces_are_consistent`でPython/ Debian version変換、両helper metadata、両SBOM、verifier、production helper compatibility allowlistの同期を自動検査する。
- [ ] `debian/changelog`を`UNRELEASED`から対象distributionへ変更し、release日時と変更点を確定する。

## 2. Source、license、SBOM

- [x] Ubuntu 26.04のremote helper dev compositionも通常userで環境SBOMを採取し、[証拠と復元確認を保存](validation/phase6-remote-sbom-2026-09-05.md)。最終release artifactの検証とは区別する。

- [x] local dev compositionの両VM installed環境SBOM/copyrightとQt package metadataを採取・reviewし、[証拠を保存](validation/phase6-vm-sbom-qt-review-2026-09-05.md)。PySide6のGPL例外表記を補正。これは最終release、remote helper環境、全license obligationの完了を意味しない。

- [x] project-owned sourceとassetsをMITとし、`LICENSE`と`debian/copyright`のholderを`NBE03xxx`へ一致させた。
- [x] vendored third-party codeがないことをtracked file一覧とpackage構成で確認した。
- [x] runtime直接依存とupstream license sourceを`THIRD_PARTY_NOTICES.md`へ記録した。
- [x] CycloneDX 1.6の直接依存SBOMをlocal/remote package別に作成し、各debの`/usr/share/doc/<package>/`へ収録した。
- [ ] Ubuntu 26.04とDebian 13のclean installでAPTが解決した全推移依存のpackage/version/source/licenseを採取し、release artifactごとのresolved-environment SBOMを作成する。
- [ ] Debianの各installed packageに対応する`/usr/share/doc/<package>/copyright`を確認し、特にPySide6/Qtの追加third-party licenseをreviewする。
- [ ] 最終binary debを展開し、未申告の実行形式、共有library、vendored module、生成assetがないことを確認する。

採取ツール`packaging/collect-installed-sbom.py`と[手順](validation/phase6-installed-sbom-2026-09-05.md)は整備済み。host smoke、両VMのlocal dev composition、Ubuntu remote helper dev compositionの採取を完了。全installed packageのsupersetを採取するため、artifact同一性・APT logとの関連付け・対象OSのmanual license reviewは別途必要。

直接依存SBOMは依存制約を表し、APTが選ぶ推移依存の正確なversion一覧ではない。release時は両方を添付する。

## 3. Reproducible build set

2026-09-09の`0.1.0` candidate compositionで、commit `4722cfa`からlocal/remote debを2回ずbuildして両方のbyte一致とverifier成功を確認した。local SHA-256は`25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181`、remoteは`45dcd8eb852317aed1da212a7bb0c1f3d008aee5d1aae38b09f980df8e56a1d1`。展開監査でELF/shared library、bytecode cache、third-party vendored moduleがないことも確認した。`UNRELEASED`解除後の最終commitから再実行するため、下記の最終artifact項目は未完了のままとする。詳細は[composition記録](validation/phase6-0.1.0-candidate-composition-2026-09-09.md)を参照する。

- [ ] clean checkoutまたはreview済みworktreeで全testとbuildを行い、未追跡fileがartifactへ混入していないことを確認する。
- [ ] local debを`dpkg-buildpackage -us -uc -b`で作成する。
- [ ] remote helper debを`packaging/remote/build-deb.sh`で作成する。
- [ ] `packaging/verify-deb.sh`と`packaging/remote/verify-deb.sh`を両artifactへ実行する。
- [ ] package name/version/architecture/dependency、root owner/mode、isolated launcher、PolicyKit fixed helper、desktop/icon、copyright/notices/SBOMを展開後に確認する。
- [ ] 同じsource commitから2回buildし、差異を比較する。差異がある場合は原因を記録し、少なくともpayload内容が一致することを確認する。
- [ ] source commit ID、build host、toolchain、両debのSHA-256をrelease記録へ保存する。

必須検査:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m compileall -q src tests setup.py
bash -n packaging/verify-deb.sh
bash -n packaging/remote/build-deb.sh packaging/remote/verify-deb.sh
desktop-file-validate packaging/desktop/io.github.nbe03xxx.llm-manager.desktop
python3 -m json.tool packaging/sbom/llm-manager.cdx.json >/dev/null
python3 -m json.tool packaging/sbom/llm-manager-remote-helper.cdx.json >/dev/null
git diff --check
```

## 4. OS lifecycle Gate

各VMの開始stateとpackage集合を保存し、Gateが追加したartifact/packageだけを明示cleanupする。利用者data、Secret Service、SSH trust、既存systemd unitをpurge対象へ含めない。

2026-09-09にcommit `4722cfa`由来の`0.1.0` local candidateをUbuntu 26.04一時snapshotで検証した。旧`0.1.0~dev0-1`からのupgrade、reinstall、remove、fresh install、purge、`dpkg -V`、隔離import、通常user offscreen Qt起動、owner/mode、dpkg管理外backup保持に成功した。snapshot復元後はpackage集合・旧package・backup hashが開始値と一致し、一時snapshot/artifact/logを削除した。Wayland実display/menuと`UNRELEASED`解除後の最終artifact再実行が残るため、下記項目は未完了のままとする。詳細は[Ubuntu lifecycle記録](validation/phase6-0.1.0-ubuntu-lifecycle-2026-09-09.md)を参照する。

同日に同じlocal candidateをDebian 13のpackage未導入状態で検証した。fresh install、reinstall、remove、再fresh install、purge、`dpkg -V`、UID 1000 offscreen Qt起動、owner/modeに成功した。pflash NVRAM形式により内部snapshotが安全に拒否されたため、APT simulationでcandidate＋新規依存11件を固定し、`autoremove`を使わず全12件を明示purgeした。終了時の2236 packageと集合SHA-256は開始値に完全一致し、artifactを削除してVMをshut offへ戻した。実display/menu、旧版からのupgrade、最終artifact再実行が残るため、下記項目は未完了のままとする。詳細は[Debian lifecycle記録](validation/phase6-0.1.0-debian-lifecycle-2026-09-09.md)を参照する。

- [ ] Ubuntu 26.04: local debのfresh install、Wayland通常user起動、menu起動、reinstall、upgrade、remove、purgeを最終artifactで確認する。
- [ ] Debian 13: stock Python/PySide6でfresh install、通常userの実display/menu起動、reinstall、upgrade、remove、purgeを最終artifactで確認する。
- [ ] Ubuntu 26.04 SSH先: remote helperのfresh install、readiness、reinstall、upgrade、remove、purgeと、dpkg管理外backup/key保持を最終artifactで確認する。
- [ ] 両OSでlocal launcher/helper/desktop/icon/copyright/notices/SBOMのowner/modeを確認する。
- [ ] remote helperでprivate runtime/copyright/notices/SBOMのowner/modeと、local GUI/PolicyKitが混入しないことを確認する。
- [ ] Gate終了後のpackage集合、VM state、一時artifact、HTTP server、test key/configが開始前へ戻ったことを記録する。

## 5. Functionalとsecurity Gate

2026-09-06追加: [認可Apply内のorigin採取と管理者専用setup](validation/phase6-root-apply-capture-setup-2026-09-06.md)を接続し、774件のbuild内testとdev deb verifyに成功した。[Ubuntu installed OS Gate](validation/phase6-root-apply-capture-installed-os-gate-2026-09-06.md)で明示setup、再初期化拒否、認可Apply前の暗号化採取・復号、terminal receipt、replay拒否とsnapshot cleanupも完了。以下の過去reviewで残件だったApply採取・明示setup入口は実装・installed検証済み。

2026-09-06追加: [root所有backupのbounded inventoryと明示GUI workflow](validation/phase6-root-restore-inventory-workflow-2026-09-06.md)を実装。各mutationをone-shot lock/hash/receiptで直列化し、外部validationから別rollbackまでを長時間特権lockでatomicとは扱わない方針を確定した。一覧→review→最終同意のsession接続、通常main windowへのavailability-gated登録、Ubuntu Qt Gateは完了した。

2026-09-08現在: root restoreは専用origin/key/store/coordinator/executor/service、review/execute CLIとclient、独立PolicyKit action、最終同意Qt境界まで実装済み。UbuntuのQt runtime Gate、[installed deny/provisioning Gate](validation/phase6-root-restore-installed-deny-provisioning-2026-09-06.md)、[valid requestによるdisposable OS mutation/service Gate](validation/phase6-root-restore-valid-os-gate-2026-09-06.md)に加え、[active desktop interactive PolicyKit Gate](validation/phase6-root-restore-interactive-policykit-2026-09-08.md)を完了した。production allowlistへ`LOCAL_ROOT`を追加し、既定空集合とSSH routeのfail-closedは維持した。

local root手動restoreの公開条件を[コードと照合](validation/phase6-root-restore-route-review-2026-09-06.md)した。専用backup証拠、preflight adapter、executor、immutable result、製品Applyからのorigin採取、明示provisioning、mutation単位の排他、通常GUIでの選択から最終同意までの接続、installed OS Gate、active desktop PolicyKit prompt/cancel/auth、正規要求とstatus照合まで完了した。

- [x] security/privacy code reviewでsecret redaction、audit非露出、bounded subprocess output、GUI error上限、root helper出力破棄を確認した。
- [x] 利用者向け`Backup・Rollback・Recoveryガイド`を公開routeとfail-closed routeに合わせて作成した。
- [ ] 最終artifactでlocal user Apply/rollback/manual restoreのGUI Gateを再実行する。
- [ ] 最終artifactでSSH user Apply/rollbackと切断後immutable result照合をGUIから再実行する。
- [x] release scope外のlocal root/SSH root ApplyとSSH user/root restoreがproduction allowlistに含まれず、経路別の固定理由でI/O前にfail closedとなることを確認した。local root手動restoreは公開Gate完了済み。
- [ ] secret corpus、symlink/path traversal、owner/mode、stale approval/hash、PolicyKit deny/cancel、SSH fingerprint変更を最終commitで再実行する。
- [x] backup key loss、片側copy loss、`RECOVERY_REQUIRED`、restore `failed`/`unknown`の利用者手順を[acceptance review](validation/phase6-recovery-procedure-acceptance-2026-09-07.md)する。

## 6. Checksum、署名、公開

- [ ] release setの両deb、source archive、直接依存SBOM、resolved-environment SBOMに対して`SHA256SUMS`を作る。
- [ ] release専用OpenPGP keyのfingerprintと保管責任者を決める。秘密鍵をrepository、VM、artifact、ログへ置かない。
- [ ] `SHA256SUMS`へASCII armored detached signatureを作成し、別環境でfingerprint指定の検証を行う。
- [ ] Git tagを同じkeyで署名し、tagがbuild source commitを指すことを確認する。
- [ ] release notesへsupported OS/version、公開route、既知制限、upgrade/uninstall、recovery guide、checksum検証方法、signing key fingerprintを記載する。
- [ ] 公開先から全artifactを再取得してchecksum、署名、package verifierを再実行する。

署名鍵は現時点で未指定のため、署名と公開はblockerである。鍵を自動生成したり既存の個人鍵を推測選択したりしない。

## 7. Release判定

未完了項目を「既知制限」だけで代替しない。release scopeから外す場合は、実装上もその経路をI/O前にfail closedとし、要件と受け入れ条件を更新してreviewする。全必須項目、artifact hash、署名検証、OS cleanup evidenceが揃った時点でMVP release候補とする。


## Root restore review producer（2026-09-06）

root側review再計算producerを追加。独立caller/host、root-owned origin、現在のtarget、AEADを照合して専用reviewを保存する。元Apply manifest hashをoriginとAEADへ追加。新規14 test、全653 test（630成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-review-2026-09-06.md`。専用PolicyKit action/CLIとGUI consentは未接続であり、既存Apply actionを流用しない。次もPhase 6: 専用認可/dispatch、全製品mutatorの同一target lock、PolicyKit/OS/Qt Gate。実設定・service・VM・SSH未操作、root route非公開、変更は未コミット。


## Root restore review CLI（2026-09-06）

専用root restore review CLIと固定dir_fd composition、独立PolicyKit action review-system-restore、isolated launcher、deb install/manpage/検証scriptを追加。preview/approveのみで復元実行はない。全661 test（638成功・23 skip）、compileall/shell/desktop/diff成功。詳細: `docs/validation/phase6-root-restore-review-cli-2026-09-06.md`。実PolicyKit/installed deb/GUIは未検証。次もPhase 6: GUI consentと呼出し、専用実行認可/CLI、全mutator lock統合、OS/Qt Gate。root mutation route非公開、実設定・service・VM・SSH未操作、全変更未コミット。
