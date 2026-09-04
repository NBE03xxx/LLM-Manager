# Phase 6 SSH user real VM Gate — 2026-09-05

## Environment and trust

Ubuntu 26.04 desktop VM `ubuntu26.04`でOpenSSH Serverを起動し、VM user `yoshimi`（UID 1000）へ公開鍵BatchMode接続した。guest agent側とnetwork側のED25519 fingerprintはともに`SHA256:icwHdGrzhWtopJvu38FgzWxnenrYn3249M1dr7dRLnA`で一致した。

remote helper artifact SHA-256は`a86c6d6c7c02fb437af59442738a07623ce003e9bff35be99f6d531239a11acf`。VMへ`llm-manager-remote-helper` 0.1.0~dev0を導入後、production strict probeはprotocol 1、root-owned fixed helper/metadata、mode、content hash、canonical metadataを検証して`READY`を返した。sudoはpasswordlessではなく、外部Ptyxisだけで対話認証した。

## Real Apply and automatic rollback

事前に3つのOpenCode config候補がすべて不存在であることを確認し、`/home/yoshimi/.config/opencode/opencode.jsonc`だけをGate対象とした。VMにOpenCode本体は導入せず、production既定`ProductRuntimeValidator`を変更しない注入seamからGate validatorを使用した。

実production compositionはstable SSH snapshotをlocal AES-GCM backupへ保存し、sudo remote helperでroot recovery copyを作成した後、unprivileged fixed helperで31 byteの一時configをApplyした。Gate validatorがpayload hashをremote readで確認して意図的にFAILEDを返し、別hash-bound rollback requestが作成済みファイルを削除した。最終結果は`ROLLED_BACK`、`apply_observed=true`、`target_exists_after=false`。

- backup ID: `ssh-user-283c9ad2481e48fe8670c9cba2b3b1f1`
- remote copy: `/var/lib/llm-manager/backups/0ed7ee8fc7dda664477c39bf/ssh-user-283c9ad2481e48fe8670c9cba2b3b1f1`
- local manifest、attempt/receipt、audit、journalは所有者限定modeで生成・検証した

実行後、host側のGate専用`/tmp` state/runtime/scriptとVM user stagingのApply/rollback IDを削除し、target不在を再確認した。remote root copy、`remote-master-v1.key`、helper package、SSH Server、公開鍵は後続のdisconnect reconciliation Gate用に一時保持する。availabilityは未公開のままである。

## Observed fail-closed preflight

最初に`yoshimi@192.168.122.48`をaliasとして試した際、`@`を許可しないremote protocol host ID境界がrequest生成前に拒否し、local backupだけを残してApplyしなかった。SSH configを変更せず、同名local/remote userのsystem OpenSSH既定を使ってaliasを`192.168.122.48`へ限定し、protocol-safe host IDで再実行した。失敗時local artifactは削除済みで、remote staging、root backup、key、target mutationは発生しなかった。
