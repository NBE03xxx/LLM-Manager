# Phase 6 ff7913b Ubuntu local/remote lifecycle — 2026-09-13

commit `ff7913bb97e896f7992720b9a43c2382970a5fc8`から再現buildした両candidateを
Ubuntu 26.04の別々の一時snapshot内で検証した。両Gateに成功し、各snapshotをrunningへ
復元後、package/manual/保全path inventoryが開始値と完全一致した。一時snapshotは削除済み。

## Artifact

- local: `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`
- remote: `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d`
- 保持先: `/tmp/llm-manager-candidate-ff7913b-20260913/`

## Remote helper

歴史的source commit `88542323d250e8e9e18bc11e3ed0e093ade3f396`から今回buildした
`0.1.0~dev0`をupgrade前提として導入した。そのdebのSHA-256は
`3fe79afe4e1d72ca8e9dfea94cd514154a2fdb099d79671174a7601e44adf52f`。
過去の旧版buildとはhashが異なるため、今回のartifact identityに記録した。

旧版からのupgrade、reinstall、remove、fresh install、purgeを確認した。
各導入境界で`dpkg -V`、canonical readiness metadata、root owner/mode、private runtimeの
bytecode不在、local GUI launcher/desktop/icon/PolicyKit非混入に成功。
保全pathは全段階で不変。purgeと一時debの削除後、snapshot復元前にもbaseline完全一致。

## Local deb

開始時の`0.1.0~dev0-1`からのupgrade、reinstall、remove、fresh install、purgeに成功。
installed moduleをUID 1000・Python isolated modeでimportし、英日catalogを確認した。
system Qt offscreenでMainWindowの表示と通常closeを確認した。
全5段階のinventoryを照合し、他package/manual集合と既存設定・backupが不変であることを確認。
`dpkg -V`、`dpkg --audit`、`apt-get check`も成功した。

今回はmenu操作やWayland実画面の再検査ではない。local artifactは9月12日の英日AT-SPI
検証と同じhashであり、当該証拠を同一artifactの結果として関連付けられる。

## 証拠・残件

`remote-helper-ff7913b-2026-09-13/`と`ubuntu-lifecycle-ff7913b-2026-09-13/`に
identity、APT simulationとgzip log、inventory、検証結果、実行script、SHA256SUMSを保存した。
実行入口は`lifecycle-ff7913b-2026-09-13.py`で、既存Gateの検証関数を再利用し、
出力path、snapshot名、artifact/hashを今回用に置き換えた。

Ubuntuはrunningを維持し、既存Phase 4 snapshotを保持。Debianは操作していない。
新candidateのDebian lifecycle、SSH機能、SBOM等を継続する。UNRELEASEDを維持しており、
最終release artifact反復、署名と公開は未完了。
