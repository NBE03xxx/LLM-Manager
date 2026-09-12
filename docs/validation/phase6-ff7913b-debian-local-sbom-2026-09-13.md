# Phase 6 ff7913b Debian local環境SBOM — 2026-09-13

ff7913b由来local deb（SHA-256
`351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`）をDebian 13へ
fresh installし、UID1000からinstalled環境SBOMとcopyright原文を採取した。

- APT simulationで新規追加集合を実行時に固定: candidateを含む12件
- baseline/installed package: 2236 / 2248件
- copyright欠落: なし
- collector exit: 0
- artifact hash、内外checksum、inventory/TSV/CycloneDX相互整合性: 検証成功
- license review完了判定: false

追加集合は`libclang1-19`、`libpyside6-py3-6.8`、`libshiboken6-py3-6.8`、
`llm-manager`、`python3-bcrypt`、`python3-cffi-backend`、`python3-cryptography`、
`python3-jeepney`、`python3-pyside6.qtcore`、`python3-pyside6.qtgui`、
`python3-pyside6.qtwidgets`、`python3-secretstorage`。過去記録の12件を前提にせず、今回の
simulation結果と開始時package集合の非交差を確認して固定した。導入後の差分はこの集合と一致し、
既存package行と保全pathは不変だった。

証拠は`sbom-ff7913b-debian-local-2026-09-13/`に保存した。archive内にcandidate identity、
collector結果、package一覧、SBOM、copyright/common-license原文と内側checksumがある。同directoryに
APT install/purge simulationと圧縮log、baseline、導入時/cleanup後inventory、host verifier結果、
全fileのSHA256SUMSを保存した。host verifierは別実行でも成功した。

このVMはpflash NVRAM形式のため内部snapshotを作成していない。`autoremove`を使わず、今回固定した
12件だけを明示purgeした。cleanup後のpackage/manual/保全path inventoryは開始値と完全一致し、
`dpkg --audit`は空、`apt-get check`は成功、転送したdeb/collector/archive/採取treeは削除済み。
VMは`192.168.122.239`でrunning、UID1000 session 2はWayland/active/unlockedを維持した。

両OSのQt/PySide6原文比較とlicense review、SSH等の残Gateを継続する。UNRELEASED候補の証拠であり、
最終release SBOMと全license obligationの完了を意味しない。
