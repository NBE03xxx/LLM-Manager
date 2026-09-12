# Phase 6 ff7913b Debian lifecycle / AT-SPI — 2026-09-13

commit `ff7913bb97e896f7992720b9a43c2382970a5fc8`由来local candidateをDebian 13で
検証した。SHA-256は`351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`。

## 結果

- APT simulationで候補と新規依存の計12件を固定し、既存packageの更新・削除がないことを確認。
- fresh install、reinstall、remove、再fresh install、purge成功。
- installed packageの`dpkg -V`、UID1000 userのisolated import、英日catalog照合成功。
- Debian stock Qt 6.8系の通常Waylandセッションで、英語・日本語のアプリを起動。
- 各combo boxの用途description、label_for関係、focusable/enabled状態、主要表示をAT-SPIで確認。
- 内部page/scroll/widget ID非露出、Alt+F4によるexit 0と対象アプリ不在を確認。
- lifecycle各段階で既存package・manual集合と保全path不変。
- 追加12件のみ明示purge後、package/manual/設定・SSH・backup関連inventoryがbaseline完全一致。
- `dpkg --audit`無出力、`apt-get check`成功。転送deb削除、両VM runningを確認。

## 証拠と限界

`debian-ff7913b-2026-09-13/`にidentity、APT simulation/gzip log、各inventory、英日raw
AT-SPI tree・summary・exit結果、cleanup結果、VM/session状態、SHA256SUMSを保存した。
`debian-ff7913b-2026-09-13.py`は既存Debian lifecycleとAT-SPI検査関数を再利用し、
対象VM・通常user・artifact/hash・出力先を固定している。

snapshot/NVRAM変更やautoremoveは行わず、導入前に確定した追加分だけを削除した。
今回の起動は通常userからinstalled launcherを直接呼び出したもので、desktop menu操作や
画面画像の目視確認、Orca音声の人手聴取を再実施したという意味ではない。
Debian旧版からのupgradeは未実施。新candidateのSSH機能、SBOM/license、最終artifact
反復、署名・公開を継続する。version 0.1.0はUNRELEASEDのまま。
