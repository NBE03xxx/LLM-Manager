# Phase 6 SSH user Apply protocol boundary — 2026-09-04

## 結論

SSH user routeのread-only前半は既存のOpenSSH host adapter、host fingerprint照合、OpenCode診断、推奨、実行直前の再取得、source-span差分生成で構成済みである。不足していたmutation境界の最初のsliceとして、unprivileged remote helperの固定`user-apply` protocolとsandbox executorを追加した。

この変更だけではproduction routeを有効化しない。local authoritative + remote recovery copyの双方の検証、rollback、runtime validation、journal/audit、GUI compositionが未接続だからである。

## 閉じた境界

- canonical requestはrequest ID、plan ID、change-set hash、backup ID、local manifest hash、host ID/fingerprint、target、before/after hash、requested/expiry時刻を束縛する。
- targetはremote user home配下の`.config/opencode/opencode.jsonc`、`opencode.json`、`config.json`だけを許可する。
- helperはroot実行、非canonical/期限切れ/tamper request、stale target、symlink、owner不一致、余分またはhash不一致のpayloadを拒否する。
- writeは既存atomic file primitiveを使用し、直後のfile hashを照合してrequest identity付きimmutable resultを保存する。
- shell text、任意argv、任意absolute path、passwordはprotocolへ含めない。
- OpenSSH transportはpayloadを先、canonical requestを最後に転送し、固定`user-apply <request-id> <request-hash>`だけを実行する。resultはbounded read後に全request bindingを照合する。
- SSH切断後の確認は同じcanonical requestから`result.json`をread-only取得し、Applyを再実行しない。

## Sandbox evidence

protocol/executorとOpenSSH transportのfocused 12件で、成功、stale precondition、target/hash tamper、root実行拒否、request-last順序、result binding、取消、read-only reconciliationを確認した。実SSH hostおよび実OpenCode設定へのmutationは行っていない。

## 次のslice

remote targetのread-only snapshotからlocal authoritative encrypted backupを生成する境界を追加した。SSH host ID/fingerprintを再確認し、allowlist済みtargetをstat→bounded read→statで観測してmetadata/hashが変化していない場合だけ、ChangeSetのbefore hashへ一致するcaptured snapshotを永続化する。通常のlocal backupも同じ永続化内部経路を使うが、外部取得snapshotだけはbefore hash一致を必須にする。

次はこのlocal正本を既存のroot-owned remote recovery copyへ接続する。remote stagingだけがSSH user所有であり、恒久copyと独立鍵はADR-0009どおりremote root所有を維持する。双方の検証成功後だけApply transportを呼ぶcoordinatorへ接続する。
