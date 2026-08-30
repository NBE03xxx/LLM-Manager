# SSH Remote Helper Positive Validation — 2026-08-30

## Scope

Phase 4のdisposable SSH target `llm-manager-gate`（Ubuntu 26.04、host `Ubuntu-dev`）へ、管理者が事前導入した`llm-manager-remote-helper` 0.1.0~dev0を使った。production OpenSSH adapter、compatibility Gate、user-only staging、外部端末sudo、root-owned production key/backendを通し、専用dummy contentのremote recovery copyだけを作成した。Ollama、OpenCode、systemd、SSH設定は変更していない。sudo passwordはアプリ、process argv、stdin、logへ渡していない。

## Result

- helper package/protocol/owner/mode/content hash: `ready`
- user-only staging uploadとrequest-last publication: 成功
- 外部端末の固定`sudo -- /usr/bin/llm-manager-remote-helper invoke-recovery ...`: 成功
- root-only key作成とAES-256-GCM remote copy: 成功
- canonical receiptのrequest/manifest/host/fingerprint/item/key/path/hash照合: 成功
- 同じrequest identityによるreceipt再取得: 成功
- helperによるuser staging明示cleanup: 成功

成功したbackup IDは`positive-gate-20260830-02`、receipt hashは`45d8ed1aac6d6aa44497dccd0f6303e39330f85474be0a307be6100b6393c335`、固定保存先は`/var/lib/llm-manager/backups/8c1e3ec6166d72b459cf9134/positive-gate-20260830-02`である。最初の試行でreceipt再読込が別request hashを生成する不具合を検出したため、作成前にcanonical request identityを保持し、同一process内の再取得で必ず再利用するよう修正した。identityを保持していない再起動後の直接loadは`remote_request_identity_unavailable`でfail closedとし、推測による別path参照を禁止した。

Gate専用root backupはdisposable VM上の検証証跡として保持した。最初の失敗試行で残ったuser stagingはallowlist済み`user-stage-remove`で明示cleanupした。

## Remaining Gate

## Restart Receipt Recovery Gate

request identity永続化後、別backup `restart-receipt-gate-20260830`で2プロセスGateを実施した。第1プロセスは外部端末sudoでhelperを1回だけ起動し、local manifest、immutable attempt、remote staging receiptを残して終了した。第2プロセスはそれらをディスクから再読込し、helperを再起動せずreceiptを取得・検証してstagingをcleanupした。

- request hash: `f01bc5e878dc68aaa55a9435c7cddf359bdedd7c60adbd95713c372d6c87c8ef`
- receipt hash: `a6da8fdd47a8b0bbaee5e80bfa605bcb901d202f5bf3fade3ed21335dff71b2d`
- process間identity一致: 成功
- helper再実行: なし
- receipt検証: 成功
- user staging cleanup: 成功（operation親directoryが空であることをread-only確認）

## Remaining Gate

転送中の実ネットワーク切断、remote retention/deletion、root journal取得、deb install/upgrade/remove/purgeは別Gateで検証する。Gate専用root backupはdisposable VM上の検証証跡として保持する。

## Remote Retention Gate

固定`invoke-retention` operationを外部端末sudo境界へ接続し、実root backendの保持評価を行った。3件のGate用backupは10世代未満のため削除されず、canonical resultをlocal immutable storeへ回収した後にuser stagingをcleanupした。

- state: `completed`
- removed backup IDs: なし
- remaining backup IDs: `restart-receipt-gate-20260830`、`positive-gate-20260830-02`、`positive-gate-20260830`
- result hash: `048d24d261e5db14e90ede1b059fee41ce73354f5e95bc60360add437daaa724`
- cleanup pending: `false`

remote deletion実Gateの前に、recovery staging cleanup後も検証済みreceiptを後続処理へ渡せるlocal immutable receipt storeを実装する。
