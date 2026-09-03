# deb packaging

## 現在のGate

Ubuntu 26.04 / Debian 13向け一般配布の先行Gateとして、local privileged helperを含む`llm-manager` binary debを構築できる。Phase 5 GUIはまだ含まないため、現時点の成果物は開発用であり公開releaseではない。

Phase 5 GUIの一般配布実行はbackup暗号化を初回既定ONとして扱う。source checkoutで暗号化OFFを初回既定にする場合だけ`LLM_MANAGER_DEVELOPMENT_MODE=1`を明示する。これは保存済みprivate backup設定を上書きせず、helperやpackage lifecycleの挙動も変更しない。

debは次をroot-owned固定pathへ配置する。

- `/usr/bin/llm-manager-helper`: mode 0755、`/usr/bin/python3 -I`で起動する限定helper
- `/usr/share/llm-manager/helper-metadata.json`: mode 0644、package/version/protocolのcanonical metadata
- `/usr/share/polkit-1/actions/io.github.nbe03xxx.llm-manager.policy`: mode 0644、上記helperだけを許可するPolicyKit action
- `/usr/lib/python3/dist-packages/llm_manager`: helperとcoreのPython package
- `/usr/share/man/man8/llm-manager-helper.8.gz`: 管理者向け境界説明

PolicyKit runtime dependencyはUbuntu 26.04とDebian 13の実package分割に合わせ、authority daemonの`polkitd`と固定launcherの`pkexec`を個別に宣言する。source package名および旧compatibility package名の`policykit-1`には依存しない。

helperはpipのconsole scriptとして導入しない。特権境界はpackage managerが所有するisolated wrapperだけとし、`PYTHONPATH`やuser site packageによるimport差し替えを許可しない。

## sandbox build

build dependencyを確認し、workspace外の一時copyでbinary packageを構築する。

```bash
dpkg-checkbuilddeps
dpkg-buildpackage -us -uc -b
```

完成artifactはinstallせずに検査する。

```bash
packaging/verify-deb.sh ../llm-manager_0.1.0~dev0_all.deb
```

検査項目はhelper/policy/metadataのarchive内root ownershipとmode、isolated shebang、PolicyKit executable path、canonical package/version/protocol metadata、runtime dependencyである。build中にも全unit testを実行する。

## remote helper別package

SSH先へ管理者が事前導入する`llm-manager-remote-helper`はlocal packageと別artifactにする。local packageはこれをinstall・upgradeせず、remote packageもGUI、local PolicyKit action、Secret Service、OpenSSH clientへ依存しない。

```bash
packaging/remote/build-deb.sh /tmp/llm-manager-remote-helper_0.1.0~dev0_all.deb
packaging/remote/verify-deb.sh /tmp/llm-manager-remote-helper_0.1.0~dev0_all.deb
```

remote wrapperは`/usr/bin/python3 -I`で起動し、import前にbytecode生成を無効化して、package内のroot-owned private runtime `/usr/lib/llm-manager-remote-helper`を固定でimportする。privileged wrapperはdpkg管理外のroot-owned `__pycache__`を生成してはならない。artifact Gateはwrapper、canonical metadata、private runtimeのroot ownershipと0755/0644 mode、依存関係、bytecode cache不在、およびlocal helper/PolicyKit/system Python packageの非同梱を検査する。OpenSSH read-only互換性Gateは固定pathのownership/mode、非symlink、content hash、canonical metadata、package/version/protocolをstaging前とhelper起動直前に確認する。disposable Ubuntu 26.04で同一版reinstall、remove、purge、再installを行い、package不在時のfail closed、再install後の`ready`、dpkg管理外root backup/keyの保持を確認した。

Python 3.14.4は検証baselineとして維持するが、正式対象Debian 13のstock repositoryから依存解決できるよう、local/remote debのsupported minimumはPython 3.13とcryptography 43.0.0、local Secret ServiceはSecretStorage 3.3.3とする。下限を変更するときはDebian 13 stock desktopで全単体テスト、暗号、Secret Service、PolicyKit、両helper artifact/lifecycle Gateを再実行する。

## Phase 5 / release前Gate

- Debian 13で正式release artifactを使う最終install/upgrade smoke test（Phase 4ではGate controlのlifecycleと正式artifactのbuild/verify/APT simulationを完了）
- GUI entry point、desktop file、icon、翻訳catalog
- release署名、repository配布、SBOMとlicense review

これらを通過するまで一般ユーザー向けdeb releaseとは扱わず、実ホストへinstallしない。
