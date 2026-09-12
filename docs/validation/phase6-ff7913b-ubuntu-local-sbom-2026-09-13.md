# Phase 6 ff7913b Ubuntu local環境SBOM — 2026-09-13

ff7913b由来local deb（SHA-256
`351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`）をUbuntu 26.04の
一時snapshotへ導入し、UID1000からinstalled環境SBOMとcopyright原文を採取した。

- installed package: 1907件
- copyright欠落: `brave-browser`、`brave-keyring`
- collector exit: 2（欠落を明示する既定動作）
- artifact hash、内外checksum、inventory/TSV/CycloneDX相互整合性: 検証成功
- license review完了判定: false

欠落2件は開始前からある非依存applicationであり、以前のUbuntu採取と同じ。
採取範囲は全installed packageのsupersetで、APTのalternative/virtual package解決を
推測したdependency edgeは含まない。既存dev packageからのupgradeであり、
clean minimal OSへの新規依存解決を主張しない。

証拠は`sbom-ff7913b-ubuntu-local-2026-09-13/`に保存した。archive内にcandidate identity、
collector結果、package一覧、SBOM、copyright/common-license原文と内側checksumがある。
同directoryにAPT simulation/install log、baseline、復元inventory、host verifier結果、
全fileのSHA256SUMSを保存し、一緒に候補へ関連付ける。

採取後はsnapshotをrunningへ復元し、package/manual/保全path inventoryが開始値と完全一致。
一時snapshotを削除した。採取treeと転送物はsnapshot復元で取り除かれた。
Debianは操作していない。

新candidateのUbuntu remote helper環境とDebian local環境の採取、Qt/license原文review、
SSH等の残Gateを継続する。UNRELEASED候補の証拠であり、最終release SBOMと
全license obligationの完了を意味しない。
