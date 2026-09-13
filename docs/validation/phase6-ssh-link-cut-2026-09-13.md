# 仮想NIC切断中の実SSHキャンセル — 2026-09-13

ホストからUbuntu VM `ubuntu26.04`（`192.168.122.48`）への専用SSH接続で、
production `SubprocessRunner` のキャンセルを確認した。製品sourceは
`ff7913bb97e896f7992720b9a43c2382970a5fc8` から変更なし。

## 方法と復旧

- 通常system SSH設定と既存の認証を使用。StrictHostKeyChecking=yes、
  UpdateHostKeys=no、ControlMaster socket共有なし。既存trustを変更しない。
- remote ready markerを受信した後、MAC `52:54:00:f8:49:29` のlive linkをdownにする。
- libvirtのdown応答を確認し、200 ms後にキャンセルを要求する。
- 300 ms後のfinallyでupへ戻す。独立processも3秒後にupを実行し、終了を確認する。
  永続NIC設定、SSH service、package、ユーザー設定は変更しない。
- remote workloadは4秒で自然終了するsleepだけ。PIDへのkillは行わない。

## 結果（1 sample）

| 確認項目 | 結果 |
| --- | --- |
| キャンセル時のlive link | down |
| キャンセル→local SSH child回収 | 32.031 ms |
| local child reap | 成功 |
| 復旧後live link | up（開始時と一致） |
| 新しいstrict SSH接続 | 成功 |
| remote有限process不在 | 確認済み |
| VM終了時state | running |

実行script: `ssh-link-cut-2026-09-13.py`。
測定値: `ssh-link-cut-2026-09-13.json`。

これはホストとguestの間の仮想ネットワーク切断試験であり、物理ケーブル断ではない。
Qt event処理、installed artifact、SSH Apply/rollback、immutable result照合は含まない。
既存の例外注入Apply Gateと本結果を合成して、完成GUI切断Gateを完了扱いにしない。

## 回帰確認

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q`
は806件中767成功、39 expected skip。`git diff --check`成功。
初回は実行側の`PYTHONPATH=src`指定漏れによるimport errorであり、指定を直して再実行した。
製品source変更なし。
