# Phase 6 ff7913b Ubuntu remote helper環境SBOM — 2026-09-13

ff7913b由来remote helper deb（SHA-256
`830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d`）をUbuntu 26.04.1の
一時snapshotへfresh installし、UID1000からinstalled環境SBOMとcopyright原文を採取した。

- APT simulationの追加は`llm-manager-remote-helper` 1件のみ、削除は0件
- installed package: 1908件
- copyright欠落: `brave-browser`、`brave-keyring`
- collector exit: 2（欠落を明示する既定動作）
- artifact hash、内外checksum、inventory/TSV/CycloneDX相互整合性: 検証成功
- license review完了判定: false

欠落2件は開始前からある非依存applicationであり、Ubuntu local採取と同じ。remote helperの導入で
manual packageに追加されたのは同packageだけで、保全pathは不変だった。採取範囲は全installed
packageのsupersetで、APTのalternative/virtual package解決を推測したdependency edgeは含まない。

証拠は`sbom-ff7913b-ubuntu-remote-2026-09-13/`に保存した。archive内にcandidate identity、
collector結果、package一覧、SBOM、copyright/common-license原文と内側checksumがある。同directoryに
APT simulation/install log、baseline、導入時inventory、復元inventory、host verifier結果、全fileの
SHA256SUMSを保存し、一緒に候補へ関連付ける。host verifierは別実行でも成功した。

採取後はsnapshotをrunningへ復元し、package/manual/保全path inventoryが開始値と完全一致。
一時snapshotを削除し、既存`phase4-pre-local-deb-20260831`だけを保持した。VMは
`192.168.122.48`でrunning。Debianは操作していない。

新candidateのDebian local環境採取、Qt/license原文review、SSH等の残Gateを継続する。
UNRELEASED候補の証拠であり、最終release SBOMと全license obligationの完了を意味しない。
