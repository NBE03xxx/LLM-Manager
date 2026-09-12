# Phase 6 実SSH待機中のキャンセル — 2026-09-12

## 結果

hostからUbuntu 26.04の通常system SSHへ接続し、production `SubprocessRunner` で
専用SSH子processを実行した。remoteのready出力を受信してから200 ms後に
`CancellationToken` をcancelし、3回とも `OperationCancelled` と子process回収を確認した。

| sample | cancel要求→local SSH回収 | 親CPU時間 |
| --- | --- | --- |
| 1 | 1.421 ms | 2.020 ms |
| 2 | 1.350 ms | 1.181 ms |
| 3 | 1.429 ms | 2.633 ms |

全sampleでlocal `waitpid` が `ChildProcessError` を返し、adapterが回収済みであることを確認。
別のread-only SSHからremote PIDの不在も確認した。
生データ: `ssh-cancel-results-2026-09-12.json`。

## 再現と測定境界

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 packaging/measure-ssh-cancel.py <trusted-alias>
```

対象IPはguest agentで `192.168.122.48` と確認した。
既存system SSH trustによるidentity検証後に、`BatchMode=yes`、
`StrictHostKeyChecking=yes`、`UpdateHostKeys=no` の専用sessionを使用する。
`-S none` で既存ControlMasterの共有を避け、他のSSH接続を停止しない。
対話認証が必要ならworkload開始前に停止する。

remote workloadはPIDをstdoutへ通知して同PIDで`exec sleep 3`を実行するだけ。
設定file、package、service、SSH trustには書き込まず、remote PIDへのkillも行わない。
remote終了は不在確認によるもので、local cancelが即座にremoteを終了させたという主張はしない。
remote workloadは接続喪失で終了しなくても3秒で自然終了する。

計測用wrapperで実Popen objectと実pipe readを観測するが、生成・read・cancel処理そのものは
元のproduction adapterへ委譲する。ready受信を確認するため、接続前cancelを成功扱いにしない。
CPU時間とcancel latencyはremote不在確認の追加SSH通信を含まない。

これは短い有限workloadの実SSHキャンセルであり、Qt event gap、長時間Agent、
Apply中の切断、immutable result照合、物理回線断の検証ではない。release SLOでもない。

## 回帰と状態

追加3 unit testで専用session/trust引数、不正alias拒否、対話認証要求時のworkload未実行を確認。
host全806件（767成功・39 expected skip）と`git diff --check`成功。
今回Qt・製品コードの変更はなく、実Qt再実行は行っていない。
両VMは開始時runningで、電源・snapshot・設定を変更せず終了した。
