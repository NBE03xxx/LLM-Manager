# Phase 6 再開・実SSH Gate前提確認 — 2026-09-11

## 検証結果

前回の未コミットQt切断照合テストと文書を保持して再開した。

- host全suite: 798件、759成功、39 expected skip（PySide6 runtime等）。
- Ubuntu stock Python / Qt offscreen: `tests.test_ui_qt_runtime`、
  `tests.test_ui_qt_app`、`tests.test_ssh_user_apply_composition` の35件すべて成功。
  source/testsだけを通常system SSHで一時treeへ転送し、終了後に削除した。
- packagingのlocal verifier、remote build/verifierの`bash -n`、
  `desktop-file-validate`、`git diff --check`成功。
- `4722cfa`由来candidateのSHA-256再照合成功:
  - local: `25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181`
  - remote: `45dcd8eb852317aed1da212a7bb0c1f3d008aee5d1aae38b09f980df8e56a1d1`

## VMの観測と保持

両VMはrunning。Ubuntuはguest agentで `192.168.122.48` と確認後、通常SSHで接続した。
既存snapshotは `phase4-pre-local-deb-20260831` のみ。snapshot操作はしていない。
Ubuntu session 3はWayland、Active=yes、State=active、LockedHint=no。
Debianのログイン済み状態は利用者申告であり、今回はdesktop画面を再検証していない。

UbuntuのSecret Serviceは利用可能、default collectionはunlock済み。
確認はavailability/lock状態だけで、鍵の読み書き・unlock要求は行っていない。
Ptyxisあり。`sudo -n -v` はinteractive authentication requiredで失敗した。
remote helper packageは未導入。`command -v opencode` は見つからず、
`/usr/bin/opencode`、`/usr/local/bin/opencode`、
`/home/yoshimi/.opencode/bin/opencode` も不在。
`/home/yoshimi/.config/opencode/{opencode.jsonc,opencode.json,config.json}` はすべて不在。

package・実設定・SSH trust・key・VM電源状態を変更していない。

## 次の判断

実OpenCodeも含む完成GUI SSH Gateに進む場合は、Ubuntuの一時snapshot内に
remote helperとOpenCodeを導入する範囲を利用者に確認し、対話sudo認証を依頼する。
認証情報はチャットやscriptへ渡さない。
現段階では導入もsnapshot作成もしていない。

過去の注入validatorによるApply/rollback検証と、今回のQt合成切断照合を
実OpenCode runtime検証または実回線切断の完了根拠として扱わない。
最終artifact/release Gateは未完了のまま。
