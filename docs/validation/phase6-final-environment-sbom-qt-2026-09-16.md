# Phase 6 final environment SBOM and Qt review (2026-09-16)

## Outcome

final source commit `5b7d4de03e495fe630deab952de043f945a22bd7`のfinal local／remote artifactを
Ubuntu 26.04 local、Ubuntu 26.04 remote helper、Debian 13 localへ一時導入し、installed environment
全体のCycloneDX 1.6 BOM、dpkg inventory、source package/version、copyright原文とcommon licenseを
採取した。3 archiveはartifact hash、内部／外部checksum、inventory、BOMをhost verifierで再検証した。

| environment | artifact SHA-256 | packages | missing copyright | release archive SHA-256 |
| --- | --- | ---: | --- | --- |
| Ubuntu 26.04 local | `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1` | 1,907 | `brave-browser`, `brave-keyring` | `e1ef61769f2c4db749353d1ebe34adc324858488b8e0c7e91df214572ec30eae` |
| Ubuntu 26.04 remote helper | `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4` | 1,908 | `brave-browser`, `brave-keyring` | `0849f2a21c4eaca844e2abd1977606c6646fb1b54dc8b6aabeaf8ec8e6c651c1` |
| Debian 13 local | `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1` | 2,248 | none | `c51602b536cc618acc2847666e13ef214e500578341291b0779c8ea8e9eea8b0` |

Ubuntuの2件は開始baselineに存在するBrave関連packageで、local／remote artifactの依存ではない。
collectorのexit 2と`license_review_complete: false`はこの欠落と、collectorが法的適合を自動判定しない
設計を表す。Debian collectorは欠落なしでexit 0だった。

## Release archive names

採用archiveを`/tmp/llm-manager-final-5b7d4de-20260916/artifacts/`へmode 0644で保存した。

- `llm-manager_0.1.0_ubuntu-26.04_environment-sbom.tar.xz`
- `llm-manager-remote-helper_0.1.0_ubuntu-26.04_environment-sbom.tar.xz`
- `llm-manager_0.1.0_debian-13_environment-sbom.tar.xz`

各archiveにはBOMだけでなく、artifact identity、package inventory、copyright原文、common license、
collector log、内部checksumが含まれる。release `SHA256SUMS`はOS／GUI／security Gate後にrelease setを
固定してから作成する。

## Qt and PySide6 review

`review-final-qt-licenses-2026-09-16.py`で3 archiveを直接読み、各環境25 binary package、
`pyside6`、`qt6-base`、`qt6-declarative`、`qt6-svg`、`qt6-translations`、`qt6-wayland`の6 source
系統を比較した。

- Ubuntu local／remoteの対象metadata、source version、copyright原文hashは完全一致。
- 全環境の選択packageにcopyright原文があり、BOM記録hashとarchive内原文hashが一致。
- PySide6の主Files節は`GPL-3-EXCEPT or LGPL-3`でQt Company GPL Exception 1.0本文を含む。
- QtBaseの主Files節は`LGPL-3 or GPL-2`。
- 直接依存SBOMのPySide6式
  `LGPL-3.0-only OR (GPL-3.0-only WITH Qt-GPL-exception-1.0)`は主選択肢の要約として整合。

機械可読結果は`qt-license-review-final-2026-09-16.json`。追加file-specific条項を単一SPDX式へ
単純化せず、全license obligationや法的適合を自動完了とは扱わない。

## Cleanup

- Ubuntu local: 専用snapshotを開始baselineへrevertし、inventory完全一致後に削除。
- Ubuntu remote helper: 別専用snapshotを開始baselineへrevertし、inventory完全一致後に削除。
- Debian local: APT simulationで追加12 packageを固定し、その集合だけを明示purge。package、manual、
  保全pathが開始baselineと完全一致し、`dpkg --audit`空、`apt-get check`成功。
- 両VMは開始・終了ともrunning。既存Ubuntu snapshot
  `phase4-pre-local-deb-20260831`は保持し、Phase 6一時snapshotは残していない。

保存済みoperationの再送、製品state注入、秘密値の読み取りは行っていない。
