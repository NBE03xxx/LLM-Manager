# Phase 6 final OS lifecycle and menu Gate (2026-09-16)

## Outcome

final source commit `5b7d4de03e495fe630deab952de043f945a22bd7`から再現buildしたlocal／remote
artifactについて、Ubuntu 26.04とDebian 13の最終lifecycle、通常Wayland menu、installed境界を
検証した。対象artifactは次の通り。

- local: `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1`
- remote: `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4`
- upgrade predecessor source: `88542323d250e8e9e18bc11e3ed0e093ade3f396`
- rebuilt predecessor local: `e302d19d6d68c32cc1de777ad766361c1afcf68b7430f7418f1f3095c546737d`
- rebuilt predecessor remote: `84213a1c9b897919c7d5625c7361be2ec7c74f4734db4fa9e50f29125141c5fa`

## Ubuntu local

- 開始baselineの`0.1.0~dev0-1`からfinal `0.1.0`へのupgrade、同一版reinstall、remove、
  fresh install、purgeに成功。
- UID1000、isolated Python import、英日catalog、Qt offscreen startup／closeに成功。
- 通常Wayland desktopでGNOME overviewを開き、`lm`検索結果にfinal packageのLLM-Manager icon/nameを確認。
  Enterで起動し、UID1000、argv `/usr/bin/python3 -I /usr/bin/llm-manager`、日本語Hosts画面を保存。
- Alt+F4で通常終了しprocess不在を確認。menu Gate内でもremove／fresh install／purgeを反復。
- package管理外の設定、SSH、backup関連pathは全段階で不変。

証拠: `ubuntu-lifecycle-final-2026-09-16/`、`ubuntu-menu-final-2026-09-16/`。

## Debian local

- package不在baselineからAPT simulationでfinal local packageと新規依存11件の計12件を固定。
- fresh install、reinstall、remove、再fresh install、purgeに成功。
- stock Python/PySide6の通常Wayland sessionで英語／日本語AT-SPI tree、label relation、combo box用途、
  focusable/enabled、内部ID非露出、通常終了を確認。
- 履歴`0.1.0~dev0`を一時導入し、final `0.1.0`へのupgrade対象が`llm-manager` 1件だけであること、
  UID1000 isolated import／Qt smoke、他package/manual/保全path不変を確認。
- GNOME overview検索でLLM-Manager icon/nameを確認し、Enter起動。UID1000、固定argv、日本語Hosts画面、
  Alt+F4通常終了を保存。

証拠: `debian-final-2026-09-16/`、`debian-upgrade-final-2026-09-16/`、
`debian-menu-final-2026-09-16/`。

## Ubuntu remote helper

- 履歴`0.1.0~dev0`からfinal `0.1.0`へのupgrade、reinstall、remove、fresh install、purgeに成功。
- canonical readiness metadata、fixed isolated wrapper、private runtime、copyright、notices、SBOMの
  root owner/mode、bytecode不在を各導入境界で確認。
- local GUI launcher、desktop/icon、PolicyKit action、system Python packageの非混入を確認。
- dpkg管理外のbackup/keyを含む保全pathは全段階で不変。

証拠: `remote-helper-final-2026-09-16/`。

## Cleanup and integrity

- Ubuntuのlocal lifecycle、local menu、remote helperは別々の専用snapshotで実行。各Gateでsnapshotを
  running baselineへrevertし、package/manual/保全path inventory完全一致後に削除した。
- Debian各Gateは開始前の追加集合を固定し、`autoremove`を使わず追加12件だけを明示purge。
  package/manual/保全pathとWayland sessionが開始値へ完全一致した。
- `dpkg --audit`は空、`apt-get check`成功、転送deb／test directory／対象process不在。
- 両VMは開始・終了ともrunning。Ubuntu既存snapshot `phase4-pre-local-deb-20260831`を保持し、
  Phase 6一時snapshotは残していない。
- 6証拠directoryの`SHA256SUMS`をhostで全件検証した。

GUI画像はfinal artifactのmenu検索と起動画面を目視確認した。保存済みmutation operationの再送、
設定／approval注入、秘密値読み取りは行っていない。
