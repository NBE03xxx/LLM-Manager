# Phase 6 installed environment SBOM collector — 2026-09-05

## 結果と範囲

`packaging/collect-installed-sbom.py`を追加した。dpkgの導入済みpackage全体をCycloneDX 1.6とraw inventoryへ記録し、binary/source version、architecture、Pre-Depends/Depends/Provides、copyright原文・参照先・SHA-256、common-licenses、os-releaseを保存する。導入前後ではなく**採取前後**のinventoryが一致した場合だけSHA256SUMSを作る。既存出力directoryは上書きしない。

これは推移依存を含む環境全体のsupersetである。APTのalternative/virtual package選択を推測した依存graphは出力しない。license欄もcopyrightの見出しから自動推定しない。copyright欠落時は証拠を残してexit 2。採取成功だけでmanual license reviewやrelease Gateを完了としない。

host Ubuntu 26.04で2519 packageを読み取り、2514件のcopyrightを保存した。5件（brave-browser、brave-keyring、code、gh、google-chrome-stable）のcopyright欠落を検出して期待どおりexit 2となった。これはworkstation全体のsmokeであり、製品の依存欠落とは判定しない。完全なhost inventoryは一時領域だけに保存し、repositoryには件数とhashの要約を記録した。

- 要約: `phase6-installed-sbom-host-2026-09-05.json`
- 一時証拠: `/tmp/llm-manager-sbom-host-20260905/`（永続release artifactではない）
- [CycloneDX公式1.6 schema](https://github.com/CycloneDX/specification/blob/1.6/schema/bom-1.6.schema.json)を取得し、hostの既存jsonschema Draft7Validatorで生成BOMを検証: PASS。dependency installなし。
- 全537 test: 514成功・23 skip。compileall、packaging shell syntax、desktop validation、diff check成功。

## Qt copyrightの予備確認

hostのlibqt6core6t64/libqt6gui6/libqt6widgets6は6.10.2+dfsg-7、sourceはqt6-base。同一のdistribution copyrightであることをhashで確認した。Files節にはQt本体以外にもdouble-conversion、freetype、harfbuzz、libpng、pcre2等があり、単一のLGPL表示だけでは原文の全範囲を表さない。source copyrightにはtests/examplesや他platformの記述も含まれるため、その全項目をinstalled binaryに含まれると断定しない。

[Qt公式のQt for Python 6.10 license一覧](https://doc.qt.io/qtforpython-6.10/licenses.html)も追加third-party termsを個別に掲載している。対象VMで実際に導入したPySide6/Shiboken/Qtのcopyrightとbinary構成を照合する必要がある。hostにはPySide6がないため、**対象OSのQt package license reviewは未完了**。

## 次の採取手順

1. 最終artifactをfreezeし、VM開始state、全installed inventory、artifact SHA-256、APT install logを保存する。通常の承認済みlifecycle Gate内で実施する。
2. local/remote artifactのpackage/version/architectureがdpkgのinstalled identityと一致することを確認し、APTのbroken dependencyがないことを確認する。
3. 対象VM内で通常userから次を実行する（outputは新規path）。追加Python依存は不要。

   ```bash
   /usr/bin/python3 -I collect-installed-sbom.py --output /tmp/llm-manager-installed-evidence
   ```

4. SHA256SUMSと全証拠を取得しchecksumを検証する。exit 2ならreview.jsonの全欠落を調査する。artifact hash、Git commit、APT log、前後inventoryと関連付ける。このツール単体はartifactとの同一性を保証しない。
5. PySide6、Shiboken、QtCore/Gui/Widgets、platform pluginおよび依存libraryの原文をreviewし、対象binaryとlicenseの対応を記録する。共通licenseへの参照と追加noticeを確認する。全環境一覧を製品の直接依存一覧として扱わない。
6. Gateで追加したpackage/artifactだけをexact cleanupし、開始前package集合とVM stateへ戻った根拠を保存する。

開始・終了ともPhase 6。両VMはshut offで変更なし。host system SSH configもnobody:nogroup/0777のまま変更していない。次は対象VMでのartifact紐付け採取とQt license review。resolved-environment release SBOM、Debian実display、未完成route、final lifecycle、署名・公開のblockerは継続する。
