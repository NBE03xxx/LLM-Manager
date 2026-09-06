# Phase 6 VM environment SBOM / Qt package review — 2026-09-05

## 結果

Ubuntu 26.04とDebian 13で同一local dev debを導入し、実installed packageのbinary/source version、copyright原文、common-licenses、Qt関連packageの配置ファイル・ELF SHA-256・DT_NEEDEDを採取した。通常userからcollectorを実行し、deb hashとinstalled package/version/architectureを照合した。APT check成功、dpkg audit出力は空。

今回完了したのはlocal dev compositionの証拠採取とQt package metadata review。release scope/version/commitは未freezeのため、最終release SBOMや全license obligationの完了判定にはしない。remote helperのresolved environmentも今回の対象外。

## 保存した証拠

[証拠directory](sbom-2026-09-05/)に以下を永続保存した。

- `llm-manager_0.1.0~dev0_all.deb`: SHA-256 `7476651fc2a88eeddfb13ba065b2c2767dbdf06396bbc518e7725d84a6d2b832`
- `debian13-local-dev0.tar.xz`: SHA-256 `da192d6e6651dec493b70c0c1b3c019a519a9f1e2988f11d41ba1010014057c7`
- `ubuntu26.04-local-dev0.tar.xz`: SHA-256 `f477941495b288168bfe7553b51e7423c8a3861770aa71026c98ac708a1761af`
- `summary.json`: package単位のlicense見出し・copyright hashとcleanup要約。

各archiveを展開すると`llm-sbom-evidence/`に`environment.cdx.json`、`inventory.json`、`copyright/`、`common-licenses/`、`qt-package-files.json`、`artifact.json`、install/check log、前後package一覧がある。`EVIDENCE-SHA256SUMS`をそのdirectory内で検証する。license見出しはdistributionの生metadataでありSPDX正規化式ではない。

両BOMは公式CycloneDX 1.6 schemaを通過。archive内の全evidence hashを取得後に検証した。全installed packageは依存を含むsupersetであり、他のdesktop applicationも含まれる。依存解決graphやclean minimal OSとは表現しない。

| 環境 | installed package | copyright欠落 | PySide6/Shiboken | QtBase |
| --- | ---: | --- | --- | --- |
| Debian 13 | 2248 | なし | 6.8.2.1-4 | 6.8.2+dfsg-9+deb13u2 |
| Ubuntu 26.04 | 1907 | brave-browser、brave-keyring | 6.10.2-6ubuntu1 | 6.10.2+dfsg-7 |

Ubuntu collectorは期待どおりexit 2。欠落2件は開始前から存在し、製品の直接依存には含まれない。brave-browserはdpkgのファイル一覧に`/opt/brave.com/brave/LICENSE`を持つが、今回の標準copyright採取では未収録。環境全体のlicense evidenceが完全とは扱わない。Qt関連26 package（Debian）/25 package（Ubuntu）にはcopyright欠落なし。

## Qt package metadata review

PySide6 QtCore/QtGui/QtWidgets、libpyside6、Shibokenのdistribution copyrightは各OS内で同じ原文を参照する。主たるFiles節は`GPL-3-EXCEPT or LGPL-3`であり、GPL-3-EXCEPT本文はQt Company GPL Exception 1.0を含む。旧直接依存SBOMとnoticesが例外を省略していたため、`LGPL-3.0-only OR (GPL-3.0-only WITH Qt-GPL-exception-1.0)`へ修正した。この式は主たる選択肢の要約であり、全ファイルのlicense式ではない。[SPDXの例外本文](https://spdx.org/licenses/Qt-GPL-exception-1.0.html)と照合した。

QtBaseのCore/Gui/Widgetsは各OS内で同一copyright。主たるFiles節のほか、double-conversion、freetype、harfbuzz、libpng、pcre2、Unicode、ICC、hash実装等の個別条項を含む。PySide6側にもBSD、Expat、Apache、documentationの条項がある。原文と共通licenseを保存し、単一LGPL表記へ潰さない。[Qt for Python 6.8の公式一覧](https://doc.qt.io/qtforpython-6.8/licenses.html)も利用するthird-party componentごとの確認を求めている。

ELFのDT_NEEDEDを実ファイルから確認した。PySideのQtWidgetsはQtWidgets/QtGui/QtCore、libpyside、Shiboken等へ動的依存する。QtCoreはICU、glib、zlib、double-conversion、pcre2等、QtGuiはfontconfig、harfbuzz、freetype、libpng、md4c等へ依存する。distribution libraryを製品deb内へvendoringする構成ではない。Qtのplugin/Wayland/QML等も環境一覧に含めた。

source copyrightにはtests/examples、他platform、build toolsも含まれるため、その全条項を実行時に使用すると断定しない。逆にDT_NEEDEDだけでは静的に含まれたコードやdlopenを網羅できない。最終releaseでは使用するplugin・source対応とnotice/source提供の必要範囲を確定する。このreviewは法的適合性の自動判定ではない。

## Cleanup

開始時は両VMともshut off。Debianは起動後のgreeterのみを確認し、通常userのdisplay/menu Gateは行っていない。

Debianは12 package（製品1＋依存11）を追加し、採取後にその12件だけを明示purgeした。前後のinstalled packageは2236件で完全一致、apt-mark showmanualも追加・欠落なし。既存package versionの変更なし。

Ubuntuは一時snapshot内で旧`0.1.0~dev0-1`からdev artifactへ置換。採取後にsnapshotへ復元し、旧版と1907 packageの版・状態、apt-mark showmanualの完全一致を確認。一時snapshotを削除した。

両guestのGate directory/証拠archiveをexact cleanupし、HTTP serverを停止。両VMをshut offへ戻した。実Ollama/OpenCode設定、Secret Service、SSH設定・trustは変更していない。host system SSHの未修復問題は継続する。

## 検証と次のPhase

buildの全537 test（514成功・23 skip）、local package verifier、両schema・evidence checksum検証が成功。notice/SBOMの例外条項修正はVM採取artifactより後の変更なので、同artifactに収録済みとは扱わない。修正後のcomposition buildは別hashで記録する。

現在・次ともPhase 6。次はremote helperのresolved environment採取、最終scope/version freezeに向けた未完成root/restore routeの判断、Debian通常ログイン後の実display/menu Gate、最終artifact lifecycleと署名・公開。今回のlocal dev証拠を最終releaseの検証へ読み替えない。

修正後composition: local `92c96a16a8ee68bdf1c3d6e308a839a8c95aeece2dde4647abc64db0b1c2f9da`、remote `259eb7e11cd912bf0eddd287413e3183f57cd0cfcbe290616933724816f88bb7`。両debのverifier成功。全537 test（514成功・23 skip）、compileall、shell syntax、desktop validation、JSON parse、diff check成功。修正後debも証拠directoryへ保存したが、VM再導入はしていない。directory全体の`SHA256SUMS`は整合性確認用であり未署名。
