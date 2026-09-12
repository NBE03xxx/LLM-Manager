# Phase 6 ff7913b Qt/PySide6 license review — 2026-09-13

新candidateに関連付けたUbuntu local/remote、Debian localのinstalled環境archiveを直接読み、
Qt/PySide6のbinary package、source package/version、distribution copyright原文とhashを比較した。
機械可読な全結果は`qt-license-review-ff7913b-2026-09-13.json`、再検査scriptは
`review-ff7913b-qt-licenses-2026-09-13.py`に保存した。

## 対象と結果

各環境で対象25 binary package、次の6 source系統を確認し、選択packageのcopyright欠落はない。

| source | Debian 13 | Ubuntu 26.04 |
| --- | --- | --- |
| `pyside6` | `6.8.2.1-4` | `6.10.2-6ubuntu1` |
| `qt6-base` | `6.8.2+dfsg-9+deb13u2` | `6.10.2+dfsg-7` |
| `qt6-declarative` | `6.8.2+dfsg-7` | `6.10.2+dfsg-3` |
| `qt6-svg` | `6.8.2-3` | `6.10.2-2` |
| `qt6-translations` | `6.8.2-2` | `6.10.2-1` |
| `qt6-wayland` | `6.8.2-4` | `6.10.2-4` |

Ubuntu local/remoteは対象package metadata、source version、copyright原文hashが完全一致した。
remote helperがQtへ依存するという意味ではなく、同じUbuntu desktop baselineに存在する環境全体の
superset証拠が一致したという限定である。DebianとUbuntuでbinary packageのsource別配分は異なるが、
合計はいずれも25件。`qt6-svg`、`qt6-translations`、`qt6-wayland`はversion差があっても今回採取した
copyright原文hashがOS間で一致し、`pyside6`、`qt6-base`、`qt6-declarative`は異なる原文hashだった。

## 原文review

- PySide6の主`Files: *`節は両OSとも`GPL-3-EXCEPT or LGPL-3`。
- PySide6原文は両OSとも`The Qt Company GPL Exception 1.0`本文を含む。
- QtBaseの主`Files: *`節は両OSとも`LGPL-3 or GPL-2`。
- PySide6/Qtの原文にはBSD、Expat、Apache、GFDL、MPL等のfile-specific条項が追加で含まれる。
- 直接依存SBOMのPySide6式
  `LGPL-3.0-only OR (GPL-3.0-only WITH Qt-GPL-exception-1.0)`は主選択肢の要約として整合する。

各sourceに属するinstalled binary packageが同一copyright原文hashを参照すること、BOMに記録された
hashとarchive内原文hashが一致することも再検査した。原文とcommon-licenseは各環境archiveに保持済み。

これは現candidateのdistribution metadataに基づく技術的reviewである。追加条項を単一SPDX式へ
単純化せず、dependency edge、実行時利用範囲、全license obligation、法的適合を自動確定しない。
そのため環境collectorの`license_review_complete`と最終release Gateはfalseのまま維持する。
