# Phase 6 authentication context installed UI Gate（2026-09-15）

## 結果

commit `7f846f5fb1134be7df06490f30a5216ab414ae0d`由来の新candidateを
Debian 13通常user desktopとUbuntu 26.04 SSH先へ一時導入し、認証時の
`REMOTE` / `LOCAL`表示を実画面で確認した。

| artifact | SHA-256 |
|---|---|
| local | `ecc099a6ae285d99fe1990cc1335dbff10f17019a766d8527566819f850eba9a` |
| remote helper | `4ca5e152c2738c1fa2ca92eaf5ab4802ecfd88438f15f54780117f463b9edbb2` |

## REMOTE表示

利用者が通常`qt_app.main`でSSH hostを選び、診断、Agent profile、推奨2件、review、
承認、Run Applyを操作した。remote sudo待機中に、GNOME Terminalのframe/labelとして
次の完全なタイトルをAT-SPIで取得し、`remote-screen.png`へ実画面を保存した。

`LLM-Manager — REMOTE sudo — phase6-auth-context-ui`

認証後のoperationは`committed`。`opencode.installed`と`opencode.config.parse`はpassed、
最終configは`compaction.auto=true`、`compaction.prune=true`。Applyは1回だけで、
plan、approval、transport、validation resultの注入はない。GUI historyは14状態。

## LOCAL表示

最初にQGAの`runuser`直下からread-only root backup inventoryの固定`pkexec` argvを起動したが、
logindのactive desktop session外と判定され、exit 127 `Not authorized`で認証前に終了した。
ダイアログ、helper実行、mutationはなく、この試行は表示Gateに採用していない。

終了を固定確認後、active desktopのGNOME Terminal D-Bus server内から同じread-only固定argvを
1回だけ起動した。PolicyKitダイアログのlabelとして次のpackage由来messageをAT-SPIで取得し、
`local-screen.png`へ保存した。

`LOCAL authentication is required to inspect and save an Ollama restore review; this does not restore settings`

利用者が明示的にキャンセルし、終了後に`pkexec`と`llm-manager-restore-review`のprocess不在を確認した。
端末の`LOCAL PolicyKit check`タイトルはGate harnessの補助表示であり、製品表示の合格根拠は
PolicyKit action自身の上記messageである。

## Cleanup訂正とbaseline

setup前のfail-closed検査で`local-master-v1`が1件残っていることを検出した。当初は由来不明のため
削除せず、属性・label・locked状態だけを取得した。Secret Serviceの`Created` / `Modified`は
epoch `1789394900`（2026-09-14 23:08:20 JST）で、前日の
[SSH Apply 5 sample performance Gate](phase6-ssh-apply-performance-2026-09-14.md) sample-01開始直前と一致した。
同Gate harnessは製品が使う`local-master-v1`とcleanupが検索する専用referenceに置換ずれがあり、
cleanupがこの1件を見逃していた。対応するテストbackup/state/configは前日cleanupで不在だった。

本Gate自体は別の専用referenceを使い、開始時の既存keyを読取り・再利用・削除しなかった。
本Gate cleanup後に、属性、label、作成/更新時刻、object pathを再照合して前日Gateの正確な残存1件だけを
Secret Serviceの`Delete`で削除し、検索結果が空であることを確認した。秘密値は一度も取得していない。
削除したテスト鍵は復元不能だが、対応する暗号化テストbackup/stateは存在しない。

専用key/SSH alias/key/state/config/cache、candidate packageと追加依存を削除した。
Ubuntu snapshotをrunningで復元後に削除し、Debian/Ubuntuのpackage/manual/session baselineは完全一致。
両VMはrunning、関連SSH/sudo/PolicyKit/helper processはない。snapshot復元でUbuntu時計が約1,086秒
遅れたため、NTP設定を変えず両guestのsystem clockだけを同期し、補正後は1秒以内となった。
証拠`SHA256SUMS`は全件成功した。

## 限界

実画面で確認したremote表示は対話sudo、local表示はrestore review actionの1件。
SSH loginタイトルと他2つのPolicyKit actionはunit testとcandidate展開監査で確認済みだが、
今回の実画面では開いていない。candidateは`0.1.0 / UNRELEASED`であり、final artifactではない。
release checklistは18/44（40.9%）を維持する。
