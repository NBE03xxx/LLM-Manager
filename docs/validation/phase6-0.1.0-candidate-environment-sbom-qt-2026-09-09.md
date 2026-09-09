# Phase 6 `0.1.0` candidate environment SBOM / Qt review

## 結果

commit `4722cfa5238af507deee0831bdf8a0cbe517fe99` 由来の同一 candidate set を使い、Ubuntu 26.04 の local/remote package と Debian 13 の local package について installed 環境の CycloneDX 1.6 evidence を採取した。local artifact SHA-256 は `25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181`、remote は `45dcd8eb852317aed1da212a7bb0c1f3d008aee5d1aae38b09f980df8e56a1d1` で、candidate composition 記録と一致した。

各 evidence は全 installed dpkg package の binary/source version、architecture、dependency metadata、distribution copyright 原文、common license、OS identity を含む。これは実際の installed environment を固定した dependency superset であり、APT の alternative/virtual package 選択を推測した依存 edge は主張しない。`debian/changelog` が `UNRELEASED` の candidate に対する pre-final evidence であり、公開用 final artifact の SBOM 完了とは扱わない。

## 保存した証拠

[証拠 directory](sbom-2026-09-09/) に3 archive、[要約 JSON](sbom-2026-09-09/summary.json)、`SHA256SUMS` を保存した。

| 環境 | artifact | installed package | copyright欠落 | archive SHA-256 |
| --- | --- | ---: | --- | --- |
| Debian 13 local | `llm-manager 0.1.0` | 2248 | なし | `538495818f83c898447fea0aaac3b7095021f648334bb05fd277ef7910d99b57` |
| Ubuntu 26.04 local | `llm-manager 0.1.0` | 1907 | `brave-browser`、`brave-keyring` | `a9597ac5b9a4386e379c4b8c03b077aeb41ed8735f491f8f4cc1818afa82d9cb` |
| Ubuntu 26.04 remote | `llm-manager-remote-helper 0.1.0` | 1908 | `brave-browser`、`brave-keyring` | `d0a3435396f5501b7c352cf67cd736aab184d3075b63189f3f35dd8df3687701` |

Ubuntu の欠落2件は snapshot 開始前からある第三者 application で、製品の直接依存ではない。collector は設計どおり exit 2 とし、環境全体の license evidence が完全とは表現しない。Debian は全2248 package の標準 copyright を採取できた。

各 archive 内の `llm-manager-phase6-sbom-gate/` には artifact identity/hash、APT install/check log、`dpkg --audit`、前後 package/manual 一覧、environment BOM/inventory/copyright/common-licenses、Qt package/file/hash 一覧がある。内部 `EVIDENCE-SHA256SUMS` と collector 自身の `SHA256SUMS` を host で全件再検証し、3 BOM を JSON parse した。

## install 境界

Debian は package 未導入の2236-package baseline から candidate と依存11件だけを追加した。差分は既存 lifecycle Gate の APT simulation と一致した。Ubuntu local は既存 `0.1.0~dev0-1` を `0.1.0` へ upgrade し、他 package に変更なし。Ubuntu remote は既存環境へ remote helper 1件だけを追加し、他 package に変更なしだった。

このため Debian evidence は fresh install で選択された12件と環境全体を関連付けられる。Ubuntu evidence は実 target environment の固定結果だが、依存 package が開始前から導入済みであるため「clean minimal OS で新規解決された package 集合」とは表現しない。

## Qt / PySide6 package license review

両OSでQt binding/module/pluginの選択23 binary packageに加え、PySide6/Shiboken runtime library 2 packageを環境inventoryから照合した。Qt shared object（Debian 25、Ubuntu 24）、Qt plugin/QML runtime file（Debian 56、Ubuntu 53）も記録した。計25 packageのdistribution copyrightに欠落はなく、各OS内でPySide6/Shiboken runtimeと3 binding packageが同じ原文hashを参照することを確認した。

- Debian: PySide6 `6.8.2.1-4`、QtBase `6.8.2+dfsg-9+deb13u2`
- Ubuntu: PySide6 `6.10.2-6ubuntu1`、QtBase `6.10.2+dfsg-7`
- 対応sourceは両OSとも`pyside6`、`qt6-base`、`qt6-declarative`、`qt6-svg`、`qt6-translations`、`qt6-wayland`の6系統

PySide6原文の主Files節は`GPL-3-EXCEPT or LGPL-3`で、Qt Company GPL Exception 1.0本文を含む。BSD-3-clause、Expat、Apache-2.0等の追加Files節も保持した。QtBase原文は主Files節に`LGPL-3 or GPL-2`を持ち、BSD、Expat、GFDL、GPLとQt例外、およびthird-party componentの個別条項を含む。直接依存SBOMの`LGPL-3.0-only OR (GPL-3.0-only WITH Qt-GPL-exception-1.0)`はPySide6の主選択肢の要約として整合するが、全Qt source fileのlicense式とは扱わない。

artifact展開監査で確認済みのとおりQt/PySide6/shared libraryは製品debへvendoringされず、distribution packageを動的利用する。今回もinstalled shared objectとruntime pluginを別packageのfileとして記録した。DT_NEEDED、dlopen、source copyrightのいずれか単独で実行時使用範囲や法的適合性を自動確定するものではない。

## Cleanupと残件

Ubuntuはrunning状態で一時snapshot `phase6-sbom-20260909`を作成し、local採取後にrevert、remote採取後に再revertした。限定一時fileを削除し、snapshotを削除して開始時どおりrunningへ戻した。既存`phase4-pre-local-deb-20260831`は保持した。

Debianはcandidateと新規依存11件の固定12 packageだけを明示purgeし、`autoremove`を使用しなかった。最終package数2236、sorted name/version SHA-256 `d4b4d64a2dd5ca6436291fe1425aba368765ae8d63d26ea01251184da685d35e`が開始記録と一致した。`llm-manager`不在、`apt-get check`成功、`dpkg --audit`空を確認し、開始時どおりshut offへ戻した。

通常system SSHは再確認時にhost drop-inのowner/mode不正でfail closedしたため、SSH GUI Gateは実施していない。SSH設定は変更していない。Debianに通常ログイン済みdesktop sessionがなかったため実display/menu Gateも保留した。

現在・次ともPhase 6。次はSSH環境の管理者修復、Debian通常ログイン後の実display/menu、`UNRELEASED`解除判断、final commitからの再build・lifecycle・SBOM・checksum/署名である。署名鍵は自動選択しない。
