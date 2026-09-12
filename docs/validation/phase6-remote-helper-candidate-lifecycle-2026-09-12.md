# Phase 6: updated candidate remote helper lifecycle

## 結果

Ubuntu 26.04の一時snapshot内で、source
`b15a98454ddf9e397333350d371b35cc2ed8fdd8`由来の
`llm-manager-remote-helper_0.1.0_all.deb`を検証した。
SHA-256は
`ee4930896f02e72d7097c58878e8900bdb0c11a495b90fd3c7b6e14b0af034bc`。

- 旧`0.1.0~dev0`から`0.1.0`へのupgrade、同版reinstall、remove、
  package不在からのfresh install、purgeが成功した。
- upgrade前提はversion-freeze直前のcommit
  `88542323d250e8e9e18bc11e3ed0e093ade3f396`のtracked sourceだけからbuildし、
  専用verifierを通した。SHA-256は
  `c80493117be42491921b726b05140ac606af5a806a80b75945f45a26807db882`。
  これはupgrade開始版だけに使い、新candidateのartifact証拠とは混用していない。
- 各APT simulationで変更対象がremote helper 1件だけで、依存packageの追加・更新・削除が
  ないことを導入前に確認した。`autoremove`は使用していない。
- upgrade、reinstall、fresh installの各状態でversion、`dpkg -V`無出力、
  root:rootのhelper 0755・metadata 0644、canonical metadata、private runtime、
  bytecode/cache不在を確認した。
- package file一覧にlocal GUI、desktop/icon、PolicyKit、local helper、通常Python
  dist-packagesへの配置がないことを各installed境界で確認した。

## 保全とcleanup

[証拠directory](remote-helper-b15a984-2026-09-12/)に固定path/hashを含む
検証script、artifact identity、APT simulation/実行log、各installed境界のmetadataと
package file一覧、開始・cleanup・snapshot復元後inventoryを保存した。

開始時の1913 package、APT manual 64件と、以下の監視対象14 entryを保存した。

- `/home/yoshimi/.config/llm-manager`
- `/home/yoshimi/.config/opencode`
- `/home/yoshimi/.ssh`
- `/var/lib/llm-manager`
- `/usr/local/bin/opencode`

upgrade、reinstall、remove、fresh install、purgeの全境界で監視対象の
owner/mode/hashが不変だった。guestへ転送した旧版・新candidateを削除後、
`cleaned-before-revert.json`は`baseline.json`とbyte完全一致した。
`apt-get check`成功、`dpkg --audit`は無出力。

一時snapshot `phase6-remote-helper-b15a984-20260912`をrunningへ復元し、
`restored.json`も`baseline.json`とbyte完全一致した。その後、一時snapshotだけを削除。
既存`phase4-pre-local-deb-20260831`を保持し、Ubuntuはrunning、IP
`192.168.122.48`。Debianもrunningのまま変更していない。ホストで一時buildした
upgrade開始版debは証拠へhashを保存後に削除した。

最初の実行は、simulation共通検査が意図した対象package自身のremoveも禁止したため、
実remove前に停止した。対象packageだけを許可するよう検査を修正し、snapshot内の
新candidate導入状態、version、`dpkg -V`、metadata、監視対象を再照合してremove以降を
継続した。製品側の不具合や想定外のpackage変更ではない。

## 範囲と残件

これはUNRELEASED candidateのlifecycle Gateであり、最終release artifactの完了根拠ではない。
新candidateでの別マシン間SSH切断、長時間Agent、accessibility、最終resolved-environment
SBOM/license review、UNRELEASED解除後の反復、署名・公開は未完了。
公開・push・署名は行っていない。
