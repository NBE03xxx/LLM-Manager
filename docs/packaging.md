# deb packaging

## 現在のGate

Ubuntu 26.04 / Debian 13向け一般配布の先行Gateとして、local privileged helperを含む`llm-manager` binary debを構築できる。Phase 5 GUIはまだ含まないため、現時点の成果物は開発用であり公開releaseではない。

debは次をroot-owned固定pathへ配置する。

- `/usr/bin/llm-manager-helper`: mode 0755、`/usr/bin/python3 -I`で起動する限定helper
- `/usr/share/llm-manager/helper-metadata.json`: mode 0644、package/version/protocolのcanonical metadata
- `/usr/share/polkit-1/actions/io.github.nbe03xxx.llm-manager.policy`: mode 0644、上記helperだけを許可するPolicyKit action
- `/usr/lib/python3/dist-packages/llm_manager`: helperとcoreのPython package
- `/usr/share/man/man8/llm-manager-helper.8.gz`: 管理者向け境界説明

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

## 未完了Gate

- disposableなUbuntu 26.04 / Debian 13環境でのinstall、同一版再install、upgrade、remove、purge
- 実desktop sessionでのPolicyKit allow/deny/cancel
- GUI entry point、desktop file、icon、翻訳catalog
- remote helperを分離したbinary packageとprotocol互換診断
- release署名、repository配布、SBOMとlicense review

これらを通過するまで一般ユーザー向けdeb releaseとは扱わず、実ホストへinstallしない。
