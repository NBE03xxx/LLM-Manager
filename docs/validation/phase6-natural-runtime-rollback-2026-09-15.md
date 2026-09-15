# Phase 6 通常GUI SSH自然runtime障害rollback — 2026-09-15

## 結果

Debian 13通常userの製品GUIで、Hosts→Diagnose→Agent recommendations 2件→Review→承認→
Run Applyを操作し、Ubuntu 26.04 SSH先のOpenCode runtimeがApply直後に一時利用不能となる
実条件から自動rollbackした。利用者は外部`REMOTE sudo` terminalでUbuntu側を認証した。

validation結果を追加・置換せず、production `ProductRuntimeValidator`と
`OpenCodeReadOnlyAdapter`が実際のruntime不在を検出した。

| 検査 | 結果 |
| --- | --- |
| plan / approval | 通常GUIで生成・選択・review・承認、注入なし |
| runtime障害 | `/usr/local/bin/opencode`をApply後だけ同一filesystem内へrename |
| production validation | `opencode.installed=failed/not_installed`、`opencode.config.parse=failed/not_found` |
| validation注入 | なし |
| Apply helper | 1回、exit 0、262 ms |
| rollback helper | 1回、exit 0、226 ms |
| 最終状態 | `rolled_back` |
| GUI | `Apply result: rolled_back; runtime validation failed`、履歴13画面 |
| config復元 | 開始SHA-256と一致 |
| OpenCode復元 | 同一SHA-256、0755、version 1.18.25、退避path不在 |

開始config SHA-256は
`fcbdf78f1ce1c2bb87446df5f5fc64d9b6da5fd23824881109581152bfee98a7`、
Apply後は`682128216e9141bd32169fd999804f3992827cbc902aaf6d4057fd4eecdac0ea`。
rollback後は開始値へ戻った。

OpenCode binary SHA-256は
`d91e0d33676d0839f7cde87924cd4127ea88c9d6784eea9f009a7d08bdc60eeb`。
runtime watcherはconfig mutationを`2026-09-15T23:19:10.408659916+09:00`相当で検出して
binaryを退避し、rollback後の開始hashを約2.385秒後に検出して同じbinaryを復元した。
対象config本文はruntime障害生成のために変更していない。

## Evidence binding

operation `ssh-user-14fed5e69f3344ae9879005843a2ff4b`のjournalは`rolled_back`で、
Apply request hashとrollback request hashを保持する。local AES-256-GCM manifestはcomplete、
remote recovery receiptはverified。plan、change set、host fingerprint、backup、manifest、
before/after hashの対応を照合した。

製品observerは画面、結果、transport時間だけを保存した。plan、approval、transport result、
validation result、GUI stateは注入していない。runtime watcherは設定のhash変化を監視し、
OpenCode binaryの一時renameと同一hash/modeでの復元だけを行った。これは偶発的に発生した障害
ではなく、実runtime不在を決定論的に発生させたGateである。一方、従来Gateのようにfailed
`ValidationResult`を製品validatorへ追加したものではない。

sourceはproduct commit `7f846f5fb1134be7df06490f30a5216ab414ae0d`のpre-final candidate。

| artifact | SHA-256 |
| --- | --- |
| local deb | `ecc099a6ae285d99fe1990cc1335dbff10f17019a766d8527566819f850eba9a` |
| remote helper deb | `4ca5e152c2738c1fa2ca92eaf5ab4802ecfd88438f15f54780117f463b9edbb2` |
| OpenCode 1.18.25 archive | `58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78` |

後続のrelease identity文書commitはこのpre-final debへ未収録であり、最終artifactの代替ではない。
利用者はVM内OpenCode 1.18.25の一時利用を了承した。Ubuntu snapshot復元により恒久的なversion変更は
残していない。

## Cleanup correction

継承元harnessはphase専用Secret Service referenceをcleanup対象としたが、production
compositionは固定`local-master-v1`を作成した。最初のcleanupはpackage、state、SSH、snapshot、
runtimeを正しく復元した一方、Secret Service itemについて誤ったreferenceを検索していたため、
その完了表現を採用しなかった。

Gate setupは`local-master-v1`不在をApply前にassert済み。cleanup後の非秘密property監査で
次の1件を検出した。

- object path: `/org/freedesktop/secrets/collection/login/5`
- attributes: application `llm-manager`、purpose `backup-encryption`、key-reference `local-master-v1`
- label: `LLM-Manager backup encryption key`
- created / modified: `2026-09-15T23:19:00+09:00`

operation開始直前の作成時刻と属性を照合し、秘密bytesを読まず、この正確な1件だけを
Secret Service `Delete`で削除した。削除後の同属性検索は空。validation scriptもproduction
referenceを追加監査・削除するよう修正した。証拠の`cleanup-result.json`は最初の誤った完了claimを
falseにし、訂正後cleanupを明記する。初回監査は削除前後を同じfile名へ保存して空の検索結果で
上書きしたため、端末へ保存済みだった正確な非秘密`GetAll`出力を
`production-key-before-correction-captured.json`へ構造化して固定した。秘密値は取得していない。
validation scriptは今後、削除前と削除後を別名で保存する。

## Final cleanup

- Debian package/manual/session baseline: 完全一致
- Ubuntu package/manual baseline: snapshot復元後に完全一致
- dedicated SSH key/config/state/cache/package: 不在
- Gate作成Secret Service item: 不在
- OpenCode退避path、watcher、GUI、SSH、sudo process: 不在
- Ubuntu一時snapshot: 削除済み
- VM state: Debian/Ubuntuともrunning
- historical Ubuntu snapshot `phase4-pre-local-deb-20260831`: 保持
- snapshot復元後のUbuntu約291秒遅れ: NTP設定を変えずsystem clockのみ補正
- 補正後: 両VMともhost時刻の±1秒内
- evidence `SHA256SUMS`: 全件一致

このGateで自然runtime障害によるproduction validation failureと自動rollbackは補完した。
公開checklistの親項目には最終artifact反復が残るため、進捗は19/44、43.2%のままとする。
