# Phase 6 通常SSH production診断 baseline — 2026-09-11

## 結果

通常system SSHでhostからUbuntu 26.04 VMへ接続し、production
`DiagnosticTaskFactory` によるread-only診断を直列5回測定した。
IPはguest agentで `192.168.122.48` と確認後に使用し、既存SSH trustを使用した。

- 経過時間中央値: 1614.899 ms
- 経過時間最大: 1632.497 ms
- Python process CPU時間: 9.243〜10.949 ms
- Python process lifetime peak RSS: 109992 KiB（SSH子processは含まない）
- 全sample: report `complete`、system/hardware観測あり
- 全sample: Ollama API `unavailable`、OpenCode未導入、runtime前提条件は未成立

`complete` は診断処理の完了を示すだけで、runtimeが利用可能という意味ではない。
Ollama/OpenCodeが利用可能なcomplete-workload Gateの代替にはしない。
Qt event gap、cancel応答、SSH Apply性能、長時間Agent、モデル推論は本測定の対象外。
5 sampleの単一環境baselineであり、release SLOやp95保証ではない。

生データ: `ssh-diagnosis-performance-2026-09-11.json`。
host Python 3.14.4、Linux 7.0.0-31-generic、glibc 2.43。
最初の探索測定も5回実施したが、runtime前提条件の明示fieldを追加した後の
5 sampleだけを上記の正式な記録とした。

## 再現・安全境界

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 packaging/measure-ssh-diagnosis.py <trusted-alias> --samples 5
```

sample数は1〜20、aliasは既存のSSH alias検証を通す。
production factoryの対話認証brokerを無効化し、認証が必要なら測定を停止する。
全sampleで検証済みfingerprintが同じことを確認する。
出力は選択した性能・状態fieldのみで、設定本文、alias、fingerprint、report全文は含めない。
production SSH設定を迂回せず、SSH trustやVM package/実設定/snapshotを変更していない。

## 回帰検証と次の作業

4 testでpartialの保持、対話認証なし、出力限定、identity欠落/変更拒否、
引数不正のI/O前拒否、completeとruntime利用可否の分離を検査した。
host全803件（764成功・39 expected skip）、shell構文、git diff --check成功。
今回はQtコードを変更していないため、前sliceの実Qt42件を再実行していない。

次はruntime利用可能なSSH診断/Applyの複数sample、長時間処理、実display accessibility、
最終artifactの反復Gateなど、release checklistの残件を進める。
