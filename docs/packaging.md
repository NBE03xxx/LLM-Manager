# deb packaging

## 現在のGate

Ubuntu 26.04 / Debian 13向け一般配布の先行Gateとして、PySide6 GUIとlocal privileged helperを含む`llm-manager` binary debを構築できる。GUI launcherは`/usr/bin/python3 -I`でdistribution-owned moduleを起動し、特権helperは別の固定PolicyKit境界を維持する。desktop fileとscalable iconを標準pathへ配置する。artifactのbuild/archive検査、Ubuntu 26.04のinstall/reinstall/purge・実Wayland起動、Debian 13のinstall/reinstall/purge・offscreen通常ユーザー起動は完了した。Debian 13の実display/menu起動とrelease署名等が未完了のため、まだ公開releaseではない。

Phase 5 GUIの一般配布実行はbackup暗号化を初回既定ONとして扱う。source checkoutで暗号化OFFを初回既定にする場合だけ`LLM_MANAGER_DEVELOPMENT_MODE=1`を明示する。これは保存済みprivate backup設定を上書きせず、helperやpackage lifecycleの挙動も変更しない。

debは次をroot-owned固定pathへ配置する。

- `/usr/bin/llm-manager`: mode 0755、`/usr/bin/python3 -I`で非特権GUIを起動するdistribution launcher
- `/usr/bin/llm-manager-helper`: mode 0755、`/usr/bin/python3 -I`で起動する限定helper
- `/usr/share/applications/io.github.nbe03xxx.llm-manager.desktop`: mode 0644、固定launcherを参照するdesktop entry
- `/usr/share/icons/hicolor/scalable/apps/io.github.nbe03xxx.llm-manager.svg`: mode 0644、desktop icon
- `/usr/share/llm-manager/helper-metadata.json`: mode 0644、package/version/protocolのcanonical metadata
- `/usr/share/polkit-1/actions/io.github.nbe03xxx.llm-manager.policy`: mode 0644、上記helperだけを許可するPolicyKit action
- `/usr/lib/python3/dist-packages/llm_manager`: helperとcoreのPython package
- `/usr/share/man/man8/llm-manager-helper.8.gz`: 管理者向け境界説明
- `/usr/share/doc/llm-manager/`: MIT copyright、third-party notices、CycloneDX 1.6直接依存SBOM

PolicyKit runtime dependencyはUbuntu 26.04とDebian 13の実package分割に合わせ、authority daemonの`polkitd`と固定launcherの`pkexec`を個別に宣言する。source package名および旧compatibility package名の`policykit-1`には依存しない。

helperはpipのconsole scriptとして導入しない。特権境界はpackage managerが所有するisolated wrapperだけとし、`PYTHONPATH`やuser site packageによるimport差し替えを許可しない。

## sandbox build

build dependencyを確認し、workspace外の一時copyでbinary packageを構築する。

source archiveはGit indexの実行bitを保持したまま`umask 0022`で展開する。`umask 0002`等で展開してpackage-owned launcher/scriptが0775になると、source mode Gateが意図どおり失敗するため、そのcopyをrelease buildへ使わない。

```bash
dpkg-checkbuilddeps
dpkg-buildpackage -us -uc -b
```

完成artifactはinstallせずに検査する。

```bash
packaging/verify-deb.sh ../llm-manager_0.1.0~dev0_all.deb
```

local packageには通常GUI、既存Apply helper、root restore review/status entryに加え、
専用root restore execute entryと各manpageを収録する。restore reviewとexecuteは別々の
PolicyKit actionに固定し、reviewやApplyの認証をexecuteへ流用しない。

管理者専用`llm-manager-restore-setup initialize`も収録する。effective UID 0での明示実行に限定し、PolicyKit actionやGUI launcherは追加しない。固定root stateが空の場合だけ鍵とprivate directoryを初期設定する。installやApplyから自動実行せず、既存key/backup/historyを上書きしない。local ApplyのATOMIC_REPLACEは初期設定済み鍵で元データを対象lock内に採取してから書く。通常GUI root routeは未公開。接続契約と残るOS Gateは[検証記録](validation/phase6-root-apply-capture-setup-2026-09-06.md)を参照する。

検査項目はGUI launcher/desktop/icon/helper/policy/metadata/copyright/notices/SBOMのarchive内root ownershipとmode、isolated shebang、固定desktop Exec/TryExec、PolicyKit executable path、canonical package/version/protocol metadata、runtime dependencyである。build中にも全unit testを実行する。直接依存SBOMは宣言した依存を表し、APTが解決する推移依存のversion一覧は最終OS Gateで別途採取する。

## remote helper別package

SSH先へ管理者が事前導入する`llm-manager-remote-helper`はlocal packageと別artifactにする。local packageはこれをinstall・upgradeせず、remote packageもGUI、local PolicyKit action、Secret Service、OpenSSH clientへ依存しない。

```bash
packaging/remote/build-deb.sh /tmp/llm-manager-remote-helper_0.1.0~dev0_all.deb
packaging/remote/verify-deb.sh /tmp/llm-manager-remote-helper_0.1.0~dev0_all.deb
```

remote wrapperは`/usr/bin/python3 -I`で起動し、import前にbytecode生成を無効化して、package内のroot-owned private runtime `/usr/lib/llm-manager-remote-helper`を固定でimportする。privileged wrapperはdpkg管理外のroot-owned `__pycache__`を生成してはならない。artifact Gateはwrapper、canonical metadata、private runtime、copyright/notices/SBOMのroot ownershipと0755/0644 mode、依存関係、bytecode cache不在、およびlocal helper/PolicyKit/system Python packageの非同梱を検査する。buildは`debian/changelog`由来の`SOURCE_DATE_EPOCH`を使い、同一sourceからのbit-for-bit rebuildをtestする。OpenSSH read-only互換性Gateは固定pathのownership/mode、非symlink、content hash、canonical metadata、package/version/protocolをstaging前とhelper起動直前に確認する。disposable Ubuntu 26.04で同一版reinstall、remove、purge、再installを行い、package不在時のfail closed、再install後の`ready`、dpkg管理外root backup/keyの保持を確認した。

Python 3.14.4は検証baselineとして維持するが、正式対象Debian 13のstock repositoryから依存解決できるよう、local/remote debのsupported minimumはPython 3.13とcryptography 43.0.0、local Secret ServiceはSecretStorage 3.3.3とする。下限を変更するときはDebian 13 stock desktopで全単体テスト、暗号、Secret Service、PolicyKit、両helper artifact/lifecycle Gateを再実行する。

## release前Gate

- Debian 13で正式release artifactを使う最終install/upgrade smoke test（Phase 4ではGate controlのlifecycleと正式artifactのbuild/verify/APT simulationを完了）
- Debian 13でdesktop menuからの実display起動を確認（artifact installと通常ユーザーoffscreen起動は完了）
- release署名、repository配布、SBOMとlicense review

これらを通過するまで一般ユーザー向けdeb releaseとは扱わず、実ホストへinstallしない。

## installed environment証拠の採取

最終artifactのOS lifecycle Gateで`packaging/collect-installed-sbom.py --output <新規directory>`を通常userから実行する。stdlibとdpkg-queryだけを使用し、packageを変更しない。全導入packageのCycloneDX 1.6一覧、binary/source version、copyright原文と共通license、checksumを保存する。これは依存のsupersetであり、APTの解決graphやlicense適合判定ではない。欠落copyrightはexit 2、採取中のinventory変更は失敗とする。

artifact hash/installed version/clean install logとの紐付けとmanual reviewは別途必要。詳細は[採取手順と検証記録](validation/phase6-installed-sbom-2026-09-05.md)を参照する。


## Dedicated restore review entry (2026-09-06)

The local deb now includes `/usr/bin/llm-manager-restore-review` with isolated Python, its manual page, and the separate `review-system-restore` PolicyKit action (`auth_admin`, no retained authorization). It exposes only preview and review persistence. It never dispatches restore execution, creates keys/stores, or accepts paths. Existing root-owned stores must be provisioned separately; production provisioning and GUI integration remain incomplete. The remote helper package is unchanged by this slice. The updated package verifier checks launcher ownership, mode and entry point; a newly built and installed artifact has not yet been validated.
