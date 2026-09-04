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

## Real transport disconnect reconciliation

同じVMと未作成targetを使い、production `OpenSshUserStagingRunner`、strict helper readiness gate、`UserOnlySshApplyTransport`、`UserOnlySshRollbackTransport`を実SSHへ接続した。固定helperがmutationとimmutable `result.json`保存を正常完了した直後だけ、Gate wrapperがtransport `disconnect`を返すことで「server側完了、client側応答喪失」を再現した。ネットワークやSSH Server自体は停止していない。

Applyとrollbackはいずれもinvoke回数は1回で、例外後は同じrequest ID/hashの`result.json`をread-only取得した。mutationは再送していない。Apply後に一時payloadをremote readで確認し、rollback後はtarget不存在へ戻ったことを確認した。

- Apply request hash: `d18eee27a3f8e3fb27bb87cfa3e1613b68c28b82eaa8b4d2d67debf395ab1eff`
- rollback request hash: `a45327be2b5c925bc2f4579e281ed213706dea9ede5900588e26534a5c5d8424`
- Apply helper invocation: 1
- rollback helper invocation: 1
- final target state: absent

Gate専用Apply/rollback stagingは固定cleanup経路で削除し、両operation directory不在を実SSHで確認した。root recovery copyやkeyはこのuser-only transport Gateでは変更していない。

## Observed fail-closed preflight

最初に`yoshimi@192.168.122.48`をaliasとして試した際、`@`を許可しないremote protocol host ID境界がrequest生成前に拒否し、local backupだけを残してApplyしなかった。SSH configを変更せず、同名local/remote userのsystem OpenSSH既定を使ってaliasを`192.168.122.48`へ限定し、protocol-safe host IDで再実行した。これはdisposable Gateに限った便宜であり、local/remote user名の一致は製品要件ではない。productionでは`User`、`HostName`、`IdentityFile`をsystem OpenSSH configの安全なaliasへ保持し、LLM-Managerには`@`を含まないaliasだけを渡す。失敗時local artifactは削除済みで、remote staging、root backup、key、target mutationは発生しなかった。
