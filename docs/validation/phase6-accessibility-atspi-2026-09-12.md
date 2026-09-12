# Phase 6 accessibility / AT-SPI Gate — 2026-09-12

## 結果

Ubuntu 26.04の通常Wayland desktopとsystem AT-SPI 2.60.4で、英語・日本語の
LLM-Manager accessibility treeを検査した。最初のcommit `b15a984`由来candidateでは、
combo boxのaccessible nameが現在値 `Local` / `English` / `Balanced`だけになり、用途を
示すdescriptionとlabel relationがなかった。また非表示のpage/scroll containerが
`page-hosts`、`scroll-hosts`等の内部IDを公開していた。このため初回Gateは不合格とした。

以下を修正した。

- Hosts、Language、Optimization profileの可視labelを追加し、各combo boxへbuddyを設定。
- locale切替時にlabelとcombo boxのaccessible descriptionを英日同期。
- page、scroll、placeholderの内部object nameをaccessibility nameとして公開しない。
- Qt runtime testへlabel、buddy、description、英日切替の回帰検査を追加。

修正版では英語・日本語の両treeで次を確認し、Gateに合格した。

- combo boxの現在値と用途descriptionが同時に取得できる。
- labelからcombo boxへ`label_for`、combo boxからlabelへ`labelled_by`が存在する。
- 対象combo boxと診断buttonはenabledかつfocusable。
- status、主要button、navigation、labelが選択localeの可視文言で公開される。
- `page-*`、`scroll-*`、`placeholder-*`とwidget object IDは公開されない。
- 英日ともAlt+F4でexit 0となり、出力は切り詰められていない。

## 検証artifact

修正版はcommit `8056850bf6c2747ca25dd26d006a003066ed9f3d`のtracked sourceへ、
今回の4ファイルだけを重ねた隔離sourceからbuildした。

- local deb: `/tmp/llm-manager-accessibility-fix-20260912/llm-manager_0.1.0_all.deb`
- SHA-256: `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`
- overlay: `src/llm_manager/ui/i18n.py`、`src/llm_manager/ui/qt_window.py`、
  `tests/test_ui_qt_runtime.py`、`tests/test_ui_qt_window.py`
- 隔離sourceの全806 test成功（767成功、39 expected skip）。
- `dpkg-buildpackage -us -uc -b`と`packaging/verify-deb.sh`成功。

これは未コミットoverlayを明記した修正確認用artifactであり、採用release candidateや
再現可能buildの根拠にはしない。source変更により旧b15a984 candidateは現行sourceの
候補ではなくなった。commit後に同一commitからlocal/remote両debを再現buildする。

## Ubuntu system Qt test

同じ隔離sourceの`src`と`tests`だけをUbuntuへ転送し、system Python 3.14 / PySide6
6.10.2でfocused 38 testを実行した。37件成功、PySide6が利用可能な環境では成立しない
inverse test 1件だけexpected skip。詳細出力は
`accessibility-fix-2026-09-12/ubuntu-qt-tests.txt`へ保存した。

## 証拠と復元

- 初回不合格時: `accessibility-b15a984-2026-09-12/`
  - baseline、環境、APT simulation/install、restored inventory、当時の固定Gate script。
  - assertion前にraw treeを保存しない旧scriptだったため、raw treeは証拠dirに残っていない。
    不合格を合格根拠として再利用しない。
- 修正版合格時: `accessibility-fix-2026-09-12/`
  - 英日raw tree、期待値と観測名のsummary、通常終了結果。
  - baseline、環境、APT simulation/install、Ubuntu Qt test詳細、再実行script。

Ubuntuへ変更を加える前にrunning snapshot
`phase6-accessibility-fix-20260912`を作成した。検査後はrunningへrevertし、package/manual/
保全pathのinventoryが開始値と完全一致することを確認してから一時snapshotを削除した。
既存snapshotは保持し、Ubuntu VMはrunningのまま。Debian VMは操作していない。

## 限界と残件

これはAT-SPI tree、Qtの関連付け、focusable state、通常終了の自動Gateであり、Orcaの
音声出力内容を人が聴取する試験ではない。また修正版は未コミットoverlay artifactなので、
commit後candidateおよび最終release artifactで再実行する。長時間Agent 60分Gate、
別マシン間SSH切断、最終SBOM/license、署名・公開は別の未完了項目である。
