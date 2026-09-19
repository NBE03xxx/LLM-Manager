# Release downloads

このdirectoryは、LLM-Managerの公開配布物をリポジトリ直下の決まった場所へ取得するための入口です。
binaryやSBOM自体はGit履歴へ重複格納せず、署名済みの公式GitHub Releaseから取得します。

リポジトリのトップdirectoryで次を実行してください。

```bash
./release/download-v0.1.0.sh
```

成功すると、11個の配布物が`release/v0.1.0/`へ保存されます。scriptは次を完了するまで成功を
返しません。

- HTTPS経由で固定した11 assetをdownload
- 公開鍵のprimary／signing-subkey fingerprintを完全一致で検証
- `SHA256SUMS.asc`によるmanifest署名を隔離GPG keyringで検証
- `SHA256SUMS`の9対象を全件検証

local GUI packageをinstallする場合:

```bash
cd release/v0.1.0
sudo apt install ./llm-manager_0.1.0_all.deb
```

SSH user経路用のremote helperは、取得済みdirectoryを接続先hostへ安全に転送したうえで、
そのhost上で管理者がinstallします。

```bash
sudo apt install ./llm-manager-remote-helper_0.1.0_all.deb
```

scriptは既存の`release/v0.1.0/`を上書きしません。再取得する場合は、必要なfileを保全したうえで
利用者自身がそのdirectoryを削除してから再実行してください。
