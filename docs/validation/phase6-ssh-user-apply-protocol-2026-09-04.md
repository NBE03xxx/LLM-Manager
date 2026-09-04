# Phase 6 SSH user Apply protocol boundary — 2026-09-04

## 結論

SSH user routeのread-only前半は既存のOpenSSH host adapter、host fingerprint照合、OpenCode診断、推奨、実行直前の再取得、source-span差分生成で構成済みである。不足していたmutation境界の最初のsliceとして、unprivileged remote helperの固定`user-apply` protocolとsandbox executorを追加した。

この変更だけではproduction routeを有効化しない。OpenSSH transport、local authoritative + remote recovery copyの双方の検証、切断後reconciliation、rollback、runtime validation、journal/audit、GUI compositionが未接続だからである。

## 閉じた境界

- canonical requestはrequest ID、plan ID、change-set hash、backup ID、local manifest hash、host ID/fingerprint、target、before/after hash、requested/expiry時刻を束縛する。
- targetはremote user home配下の`.config/opencode/opencode.jsonc`、`opencode.json`、`config.json`だけを許可する。
- helperはroot実行、非canonical/期限切れ/tamper request、stale target、symlink、owner不一致、余分またはhash不一致のpayloadを拒否する。
- writeは既存atomic file primitiveを使用し、直後のfile hashを照合してrequest identity付きimmutable resultを保存する。
- shell text、任意argv、任意absolute path、passwordはprotocolへ含めない。

## Sandbox evidence

`tests.test_remote_user_apply`の4件で、成功、stale precondition、target/hash tamper、root実行拒否を確認した。実SSH hostおよび実OpenCode設定へのmutationは行っていない。

## 次のslice

既存のuser-only stagingをApply用transportへ拡張し、request-last upload、固定`user-apply` invocation、bounded result read、明示cleanupを実装する。その上でdual-copy backup verificationと同一requestによるdisconnect reconciliationを接続する。
