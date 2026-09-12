# Phase 6 ff7913b Debian旧版upgrade — 2026-09-13

Debian 13 stock Python/PySide6環境で、旧`llm-manager 0.1.0~dev0`からff7913b由来
`llm-manager 0.1.0`へのAPT upgradeを確認した。

## Artifact

upgrade predecessorはcommit `88542323d250e8e9e18bc11e3ed0e093ade3f396`のtracked sourceを
新規`/tmp` treeへ展開し、`dpkg-buildpackage -us -uc -b`でbuildした。historical
`packaging/verify-deb.sh`を通過した。

| artifact | SHA-256 |
| --- | --- |
| `llm-manager_0.1.0~dev0_all.deb` | `e302d19d6d68c32cc1de777ad766361c1afcf68b7430f7418f1f3095c546737d` |
| `llm-manager_0.1.0_all.deb` | `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243` |

旧artifactはupgrade前提の検証資材であり、release candidateではない。新artifactのsource commitは
`ff7913bb97e896f7992720b9a43c2382970a5fc8`。

## 結果

開始時は`llm-manager`未導入、dpkg package行2236件。旧版fresh installのAPT simulationから
candidate＋依存11件の追加集合を実行時に固定し、既存packageとの非交差を確認した。旧版導入後は
2248件、`dpkg -V llm-manager`は空だった。

新candidateのAPT simulationは次の遷移だけを示した。

- upgrade: `llm-manager` 1件（`0.1.0~dev0` → `0.1.0`）
- new install: 0件
- remove/purge: 0件

実upgrade後も2248件で、`llm-manager`以外のpackage行、manual集合、保全pathは旧版導入時から不変。
`dpkg -V`は空。UID1000のisolated importとoffscreen Qt windowのshow/closeに成功した。

Debian VMはpflash NVRAM形式のためsnapshotを使用していない。`autoremove`は使わず、旧版導入時に
固定した12件だけを明示purgeした。終了時はpackage/manual/保全pathが2236件のbaselineへ完全一致し、
`dpkg --audit`は空、`apt-get check`成功、転送物を削除した。VMはrunning、session 2は前後とも
Wayland/active/unlockedで完全一致。

証拠は`debian-upgrade-ff7913b-2026-09-13/`に、artifact identity、APT simulation/log、全inventory、
smoke、cleanup、SHA256SUMSとして保存した。menuからの再起動、Orca音声、UNRELEASED解除後の
最終artifact反復は別Gateとして残す。
