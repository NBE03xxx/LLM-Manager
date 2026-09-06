# Phase 6 GUI deb composition and Ubuntu lifecycle Gate — 2026-09-05

## Scope

一般ユーザー向けlocal debへ、非特権PySide6 GUI launcher、desktop entry、scalable icon、Qt runtime dependencyを追加した。PolicyKit actionは従来どおり`/usr/bin/llm-manager-helper`だけを許可し、GUI launcherへ特権を付与しない。

## Artifact boundary

- `/usr/bin/llm-manager`: root-owned 0755、`/usr/bin/python3 -I`から`llm_manager.ui.qt_app.main`だけを起動
- `/usr/share/applications/io.github.nbe03xxx.llm-manager.desktop`: root-owned 0644、固定Exec/TryExec、terminal無効
- `/usr/share/icons/hicolor/scalable/apps/io.github.nbe03xxx.llm-manager.svg`: root-owned 0644
- PySide6 QtCore/QtWidgetsはDebian 13 stockのPython 3.13/PySide6 6.8.2.1組合せをdeb dependencyの最低版とする。Python 3.14向けwheelは最低版6.8.6を維持する
- privileged helper、metadata、PolicyKit actionの既存pathと分離を維持

## Verification

workspace外の一時copyで`dpkg-buildpackage -us -uc -b`を実行した。build時の全unit testに成功し、`packaging/verify-deb.sh`でlauncher、desktop、icon、helper、policy、metadataの存在、owner、mode、固定参照、runtime dependencyをarchiveから検証した。

- package: `llm-manager` 0.1.0~dev0
- artifact SHA-256: `a85915eb39d7f73d7d6bf2f125a2ed90cb62cb322591ae9c4ea963266656509f`

## Remaining release Gate

## Ubuntu 26.04 lifecycle

既存Ubuntu 26.04 desktop VMを一時internal snapshotで保護し、正式artifactをAPTで導入した。VMには旧Gate package `0.1.0~dev0-1`が存在したため、snapshot内に限り`--allow-downgrades`で`0.1.0~dev0`へ置換した。

- 宣言したPySide6 QtCore/QtWidgets依存を含むAPT install成功
- root-owned launcher/helper 0755、desktop/icon 0644を確認
- UID 1000の通常ユーザーから既存Wayland sessionへGUIを起動
- 日本語Host画面が実displayへ描画され、GUI processがUID 1000で稼働
- 同版`--reinstall`成功
- purge成功後、package query失敗と`/usr/bin/llm-manager`不在を確認

Gate後はsnapshotへrevertし、元の`0.1.0~dev0-1`導入状態を確認してから一時snapshotを削除した。Gate用deb、log、package変更はsnapshot外へ残していない。SSH Server、authorized key、known-host trustは後続Gate用に維持した。

## Debian 13 lifecycle

Debian 13 stockはPython 3.13.5とPySide6 6.8.2.1を提供する。Python 3.14用baselineの6.8.6をdebへ一律適用すると依存解決不能になることを事前監査で検出したため、Debian system packageとPython 3.13の組合せだけをsupported minimum 6.8.2.1としてversion matrixへ追加し、artifactを再buildした。

ユーザーが導入したQEMU guest agentへ標準`org.qemu.guest_agent.0` virtio channelをlive/persistent追加した。VMはpflash NVRAM形式によりinternal snapshot非対応だったため、Gate前後の全installed package集合を比較し、今回追加されたものだけを明示削除した。

- SHA-256一致後にAPT installし、stock PySide6 6.8.2.1を含む依存解決成功
- launcher/helper 0755、desktop/icon 0644、root ownershipを確認
- UID 1000の`user`からoffscreen GUIを5秒間起動し、正常継続をtimeout 124で確認
- 同版reinstall成功
- `llm-manager` purge後、Gateで追加された11 dependencyだけを明示purge
- cleanup後のinstalled package集合はGate前と完全一致（added/missingとも空）
- Gate用deb、package一覧、一時HTTP serverをcleanup

VMにはログイン済みgraphical sessionがなくdisplay outputもinactiveだったため、実display描画とdesktop menuからの起動は未実施である。Debianの公開release Gateとしてこの2点だけを残す。
