# Phase 6 remote helper environment SBOM — 2026-09-05

## 結果

Ubuntu 26.04 VMの一時snapshot内で、修正後noticeを含む`llm-manager-remote-helper 0.1.0~dev0`を導入し、UID 1000の通常userから`packaging/collect-installed-sbom.py`を実行した。全1908 installed packageのbinary/source version、dependency metadata、copyright原文とcommon-licensesを保存した。

追加packageはremote helper 1件だけ。開始前1907 packageの削除・version変更はなく、`apt-get check`成功、`dpkg --audit`出力は空。collectorは既存`brave-browser`と`brave-keyring`の標準copyright欠落により期待exit 2となった。この2件は製品の直接依存ではないが、環境全体のlicense evidenceを完全とは扱わない。

これはremote helperのdev composition採取であり、clean minimal OSや最終release artifactのresolved dependency graphではない。全installed packageは他applicationを含むsuperset。license obligation、release scope/version、最終lifecycle、SSH GUI disconnect/reconciliationの完了根拠にはしない。

## 保存した証拠と検証

[証拠directory](sbom-2026-09-05/)へ以下を保存した。

- `llm-manager-remote-helper_0.1.0~dev0_remote-gate_all.deb`: SHA-256 `259eb7e11cd912bf0eddd287413e3183f57cd0cfcbe290616933724816f88bb7`。現worktreeから再buildし、remote verifier成功。前sliceのlicense修正後artifactと同一hash。
- `ubuntu26.04-remote-dev0.tar.xz`: SHA-256 `560c9d43f5d397a1511dd06d4b30b01108b651e58a30172e96636c7831a8cc24`。
- `remote-summary.json`: schema、checksum、payload照合、package差分と復元結果。
- `remote-cleanup.json`: package/manual一覧一致、guest artifact不在、snapshot削除、停止状態の確認。

archive内の`llm-remote-sbom-20260905/`にdeb、collector source、導入前後inventory、APT install/checkとdpkg audit log、artifact identity、installed file manifestを収録した。`evidence/environment/`にはCycloneDX BOM、inventory、copyright、common-licenses、review結果がある。guestとの転送にはguest agentを使用し、送受信artifact/archiveのSHA-256を照合した。

`EVIDENCE-SHA256SUMS`の1938 fileをhostで再検証した。BOMは既存の公式CycloneDX 1.6 schemaで検証成功。installed payloadの全109 fileはdeb展開結果とSHA-256・modeが一致し、UID/GIDはいずれも0だった。package identityは`llm-manager-remote-helper 0.1.0~dev0 all installed`。directoryの`SHA256SUMS`も更新したが未署名である。

## VM復元と境界

開始時はUbuntu 26.04、Debian 13ともにshut off。Ubuntuの停止状態で一時snapshotを作成し、起動後にpackage版・状態と`apt-mark showmanual`のbaselineを保存した。採取後に停止してsnapshotを復元し、再起動してbaselineの完全一致とguest artifact不在を確認した。その後停止し、一時snapshotを削除した。Debianは起動していない。

host SSH configは引き続き`nobody:nogroup`・0777であり、変更していない。このGateをproduction system SSH経路の検証とは扱わない。実Ollama/OpenCode設定、backup/key、Secret Service、SSH trustへの操作は行っていない。HTTP serverやhost dependency installも使用していない。

## 検査と次のPhase

全537 testが完走（514成功・23 skip）。compileall、local/remote packaging shell syntax、desktop-file validation、remote deb verifier、schema/checksum/payload検証が成功した。hostのskipは主にPySide6不在による。

現在・次ともPhase 6。次は未完成root/restore routeのscope判断とversion確定、Debian通常ログイン後の実display/menu Gate、最終artifactによるOS lifecycleとrelease SBOM。SSH環境が修復されたら完成GUIの切断Gateを再開する。署名鍵は未指定のまま自動選択しない。すべての既存変更と今回の文書・証拠は未コミットで保持する。
