# Phase 6 installed GUI SSH Gate — 2026-09-11

## 環境・導入

利用者の承認に基づき、running Ubuntuに一時snapshot
`phase6-ssh-gui-20260911` を作成した。既存snapshotは保持。
開始package/manual一覧と関連pathのmode/owner/hashは
`ssh-gui-2026-09-11/baseline.json` に保存した。

`4722cfa`由来のlocal/remote候補debをhash再照合後に導入。
APT simulationは既存local packageのupgradeとremote helper追加だけで、削除なし。
導入後の両package `dpkg -V` は差異なし。
初回のguest-agent転送はOSのargv上限で失敗したため、chunkを128 KiBから32 KiBへ修正。
失敗したGate専用転送fileは再転送し、hash照合後にだけAPTへ渡した。

OpenCodeは[公式release v1.18.30](https://github.com/anomalyco/opencode/releases/tag/v1.18.30)の
`opencode-linux-x64-baseline.tar.gz` に固定。
GitHub release APIのSHA-256
`60c92147d0d86ca606dda8a77260d3c87e0ef959eb2d8dbffb34df6d8a64e063`
に一致し、archiveが単一regular file `opencode` だけであることを確認。
`/usr/local/bin/opencode` へroot:root 0755で一時導入し、UID 1000で `1.18.30` を確認した。

## Gateの境界

UbuntuのWayland GUIから同VMへのloopback SSHを使う。
snapshot内に一時鍵・専用known_hosts・`phase6-gui-gate` aliasを作成。
host keyはguest側のED25519公開鍵から固定し、StrictHostKeyChecking=yesを使用。
通常system SSH設定は読み、`-F /dev/null`等の回避は使用しない。

実installed GUI、production診断、SSH Apply factory、Secret Service暗号化local backup、
sudo root recovery copy、固定helper、製品runtime validatorを使用する。
Results画面へGate用plan/approvalを注入してApply buttonを押すため、
診断から推奨・人手reviewまでの全操作経路を検証したとは扱わない。
helperが正常終了した直後に応答喪失例外を注入する。物理回線やSSH serverは停止しない。
製品validatorは実OpenCode `--version` と設定JSONC解析を行うが、モデル推論は行わない。

## 結果

利用者がVM内の専用端末でsudo認証した。秘密情報はチャットやscriptへ渡していない。

| case | 製品validator | 結果 | 固定helper呼出し |
| --- | --- | --- | --- |
| 正常JSONC | installed/parseともPASSED | COMMITTED | Apply 1回 |
| 意図的な不正JSON | installed PASSED、parse FAILED | ROLLED_BACK | Apply/rollback各1回 |

それぞれhelper正常終了後に応答喪失例外を注入し、immutable resultのread-only照合だけで完了。
rollback後は正常設定のSHA-256
`b30b14759c0fd796fc8e6a744ccd19caf081d874d51ff1dfebb1c1938ae29088` に一致した。
可視caseのjournal終端もcommitted/rolled_backと一致。

### 検証スクリプトの修正と証拠の採否

最初の2 caseはbackendと結果widgetの文言は成功したが、画像ではHostsページが表示されていた。
`commit/` と `rollback/` はその補助証拠であり、結果ページの実表示の証明には使わない。
Resultsページの選択と`isVisible()`検査を追加した。途中でavailabilityの既定空allowlistが
Applyを無効にしたため、通常production起動と同じlocal user/SSH user allowlistへ合わせた。
この失敗はbuttonクリック前で、mutationなし。

別operation IDの2 caseで再実行し、`visible-commit/` と `visible-rollback/` に
JSON、journal、実画面画像を保存した。両画像を目視確認済み。
可視commitは既存の正常Gate設定を同じ正常本文に置換し、可視rollbackは不正本文からそれへ復元する。
全4成功operationの合計はApply 4回・rollback 2回で、同一operationのmutation再送はない。
採用した可視Gate scriptは `ssh-gui-2026-09-11/gate.py` に保存。
これはsnapshot内の専用alias/設定/認証を前提とする記録用scriptで、一般環境へそのまま実行しない。

### 製品表示修正と回帰検証

candidateの実画面ではproduction経路でも `Sandbox Apply result` と表示されていた。
sourceの英日3文言を中立な `Apply` 表示へ修正し、i18n regressionを追加。
Qt切断照合回帰にもResults選択・button/summaryの可視性assertを追加した。
画像は修正前candidateの原本であり、修正後artifactの表示証拠ではない。

- host全799件: 760成功、39 expected skip。
- Ubuntu Qt/SSH composition/i18n計42件: 全件成功。
- shell構文、desktop-file-validate、git diff --check成功。

## 復元完了

Gateプロセス不在を確認し、必要な非秘密証拠をホストへ回収後、
`phase6-ssh-gui-20260911` をrunningへ復元した。
`restored.json` は `baseline.json` と完全一致。
package/manual一覧、OpenCode対象path、SSH設定、既存root backup関連pathの
owner/mode/hashが一致し、一時snapshotだけを削除した。
検証用package、OpenCode、SSH鍵/alias、暗号化key/backup、一時設定・VM artifactはsnapshotで取り消した。
利用者の既存snapshotは保持し、Ubuntuはrunning。Debianは未変更。
証拠18 fileの`SHA256SUMS`をstrict検証済み。
2026-09-12のcommit前検査でAPT生ログのCRがGit空白検査に該当したため、
本文を変更せず`gzip -n`で`apt-install.txt.gz`へ保存し直しchecksumを更新した。
展開後の元SHA-256は`2350a3187e39492994afc2fa0cb9cae2ca99ef3dc299f972a4ae3aea3241eed0`。
ホストの今回専用CLI archive・一時script・認証待ち画像も削除した。
script原本は証拠dirへ保存し、以前のcandidate debは保持している。

## 残件

これはUNRELEASED candidateの限定Gateであり、最終artifact Gateではない。
通常起動からの推奨・人手review全経路、別マシン間のネットワーク切断、モデル推論成功、
修正後最終artifactでの反復検証、残りrelease checklistは未完了のまま。
