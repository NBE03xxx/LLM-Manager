# Phase 6 security/privacy review — 初回コード監査

## 対象と結論

2026-09-05、`06628f6`を基点とする未コミットGUI deb sliceを保持して実施した。
本記録はコード上のsecurity/privacy reviewと確認された問題の修正結果であり、MVP release全体の完了宣言ではない。
`virsh list --all`でDebian 13とUbuntu 26.04がともに停止中と確認したため、VMを起動せず独立sliceへ進んだ。実config、SSH設定、systemd、鍵、VM packageは変更していない。

## 確認した境界

| 対象 | コードと確認結果 | 限界 |
|---|---|---|
| GUI公開経路 | `ui/qt_app.py`はApplyをlocal user/SSH user、手動restoreをlocal userだけに限定。availability test群が継続成功 | 未完成root/SSH restoreを完成扱いにしない |
| プロセス起動 | `infrastructure/process.py`はexecutable allowlist、argv、`shell=False`、stdin無効、固定environment、timeout/cancel、受信中のstream別上限を使用 | 超過したprotocol出力は切り詰めずstable errorでfail closed |
| 秘密値と監査 | `infrastructure/redaction.py`、`audit.py`を確認。raw content/diff field拒否、scalar metadata redaction、0700/0600、hash chainを既存testで確認 | 同じUIDが全chainとHEADを書き換える攻撃に対する外部署名ではない。未知のsecret形式の完全検出も保証しない |
| GUI worker例外 | `ui/qt_worker.py`は例外本文を渡さずcodeと例外class名に変換 | coordinator結果内errorや同期例外を含む全表示sinkの監査は継続 |
| Backup暗号 | `backup_crypto.py`はAES-256-GCM、random nonce、AAD、key scope、size検証。`secret_service.py`は利用不能/解除拒否をerrorとして返す | 本回は実desktop Secret Serviceを再実行していない |
| 診断通信 | `adapters/ollama/readonly.py`はloopback HTTP endpointだけを許可し、credential/query/fragmentを拒否 | curl個人設定、SSH先environmentも含む通信先保証の追加監査が必要 |
| deb権限境界 | GUI launcherは`python3 -I`、PolicyKitは固定helperのみ。distribution testが成功 | 本修正を含むdebの再build・VM再Gateは未実施 |

## SEC-01: 引用符付きsecret値の部分露出 — 修正済み

従来のassignment regexはJSONの`"api_key": "..."`を認識せず、
`password='two words'`では最初の空白までしか隠さなかった。
このため、監査の通常error fieldへこうした文字列を渡すとsecretが永続化されることを合成sentinelで再現した。
実際の利用者secretの漏洩を確認したという意味ではない。

キー末尾の引用符を認識し、引用符付き値はescape・空白・改行を含めて全体を隠す。
閉じ引用符のない切れた診断も末尾まで隠す。出力は表示用の文字列であり、JSONとして再解析する用途ではない。

- `RedactionTests.test_redacts_quoted_assignments_without_leaking_value_tails`: JSON、single quote、escaped quote、改行、未終端quoteの5ケース。
- `LocalAuditLogTests.test_redacts_quoted_secrets_in_persisted_error_metadata`: 永続fileと再読込後のerror metadataにsentinelが残らないことを検証。
- 修正前は上記6ケースが失敗し、修正後は関連13 testが成功した。

## SEC-02: subprocess出力が取得後にしか制限されない — 修正済み

`SubprocessRunner.run`は`communicate()`でstdout/stderr全体を収集した後、
`_decode_limited()`で各4 MiBへ切り詰める。したがって`max_output_bytes`は返却文字列の上限であり、
大量出力する診断先に対するプロセスメモリ上限ではない。timeoutまでの出力でメモリを圧迫できる。
本回は大量出力による実測を行っていない。

selectorでstdout/stderrを並行して読み、各streamで上限を1 byteでも超えた時点で子プロセスを停止・回収し、
`command_output_too_large`へ閉じるよう修正した。途中までのprotocol payloadを正常結果として返さない。
通常の両stream収集とstderr redaction、stdout/stderr各超過、timeout時のbounded partial result、cancel、無効な上限を実subprocessで検証した。

同じfocused 13 testを、同一artifact（SHA-256
`db3570d131a022ae39d67ed7f0a3179e68605ccdae9a6cee405282898989a4fe`）から
Ubuntu 26.04 / Python 3.14.4とDebian 13 / Python 3.13.5で実行し、両方成功した。
VM内とhostの一時artifactを削除し、起動前と同じ両VM停止状態へ戻した。

## SEC-03: GUI結果とroot helperの未使用出力 — 修正済み

3つのApply coordinatorが共用する`ApplyOutcome`で、errorをGUIへ渡す前にsecret redactionと4 KiB上限を強制した。
root helperの固定`systemctl`実行はstdout/stderrを利用しないため、pipeへ収集せず`DEVNULL`へ送る。
合成secretと5 KiB超のerror、およびsubprocess引数をtestで確認した。

## 検証

- 全521 test実行、503成功・18 skip（ホストのPySide6/desktop依存Gate）。失敗なし。
- compileall、local/remote packaging shell syntax、desktop-file-validate、git diff --check成功。
- SEC-02 focused testは対応OS両方で再実行した。他のOS依存Gateの過去結果を今回の再実行結果として扱わない。

静的検索ではアプリ独自の外部HTTP、telemetry、analytics送信を確認しなかった。Ollama自動診断はloopback HTTP限定で、
remote通信はsystem OpenSSH経路に限定される。未知のsecret形式を完全に検出する保証、同一UIDによるaudit chain全体の再生成、
利用者管理のOpenSSH configとremote hostは残存trust boundaryである。

次の作業もPhase 6。利用者向けbackup/rollback/recovery文書を実装済み経路とfail-closed経路に合わせて作成し、
続いてSBOM/license/署名release checklistへ進む。
