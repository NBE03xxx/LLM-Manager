# Phase 6 修正後candidate Ubuntu lifecycle / 実display — 2026-09-12

## 結果

source commit `b15a98454ddf9e397333350d371b35cc2ed8fdd8` 由来のlocal candidate
`llm-manager_0.1.0_all.deb` をUbuntu 26.04通常Wayland desktopで検証した。
SHA-256: `292b831c5454e3a6d41b59a67145474a76b066146bebc4e7308b81a6e50ff7f8`。

- 既存 `0.1.0~dev0-1` からupgrade、同一候補reinstall成功。
- GNOMEアプリ検索で `llm` → LLM-Manager → Enterによるmenu起動成功。
- PID 7617、UID 1000、argv `/usr/bin/python3 -I /usr/bin/llm-manager` を確認。
- 日本語Hosts画面、host欄のkeyboard focus、Tab/矢印で英語への切替を実画面で確認。
- Alt+F4で通常終了し、対象process不在（pgrep exit 1）を確認。
- remove → fresh install → purge成功。各段階でLLM-Manager以外のpackage/manual集合と、
  既存設定/SSH/root backup関連pathのowner/mode/hashが開始値と一致。
- upgrade/reinstall後とfresh install後の `dpkg -V llm-manager` は無出力。
- 最終 `dpkg --audit` 無出力、`apt-get check` 成功。

installed隔離importもUID 1000で成功し、moduleは
`/usr/lib/python3/dist-packages/llm_manager/__init__.py`。
英日catalogは `Apply result: committed.` / `Apply結果: committed。` で、
旧「Sandbox」誤表記の修正が新artifactに含まれることを確認した。
これはcatalog照合であり、今回Results画面でApplyを実行したという意味ではない。

## 証拠

`ubuntu-display-b15a984-2026-09-12/` に以下を保存。

- `menu-search.png`、`menu-launched.png`、`keyboard-focus.png`、`english.png`
- `menu-process.json`、`normal-exit.json`、`installed-import.json`
- baseline、各5段階のinventory、restored inventory、`lifecycle-audit.json`
- 各APT simulationとCR原文を保持した`.txt.gz` log
- 実行・監査script `lifecycle.py`（以前の記録用vm-lifecycle.pyの共通関数を利用）
- `SHA256SUMS`

画像は目視確認済み。操作直後の未反映画像は採用せず、最終的に描画済みの画像を保存した。
実display Gateは通常メニュー起動で、前回のResults注入スクリプトは使用していない。

## 復元

開始前にpackage/manual/path情報をホストへ保存し、running一時snapshot
`phase6-ubuntu-display-b15a984-20260912` を作成した。
candidate転送後にもhashを再照合し、APT simulationで対象package以外の操作がないことを確認した。

検証終了後、snapshotをrunningへ復元。
`restored.json` と `baseline.json` が完全一致した後、今回の一時snapshotだけを削除した。
既存 `phase4-pre-local-deb-20260831` は保持。
UbuntuはWayland session 3、Active=yes、State=active、LockedHint=no。
VM内の一時deb不在、両VM runningを確認した。Debianは操作していない。

## 残件

version 0.1.0はUNRELEASEDのcandidateであり、最終release artifact Gateではない。
新候補のDebian lifecycle/実display、remote helper、SSH Apply、screen reader/長時間Agent、
最終SBOM/署名等の残件を継続する。今回production source変更はなく、
前回の806 test・再現build成功を保持し、全suiteの再実行は省略した。
