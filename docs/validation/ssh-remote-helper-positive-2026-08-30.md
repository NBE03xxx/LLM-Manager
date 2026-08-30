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

実SSH切断後のreceipt/result回収、remote retention/deletion、root journal取得、deb install/upgrade/remove/purgeは別Gateで検証する。再起動をまたぐrecovery request identityの永続化はproduction compositionへ接続するまでfail closedを維持する。
