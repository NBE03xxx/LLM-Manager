# 次チャット用引き継ぎプロンプト（2026-09-13）

以下を新しいチャットで実行してください。

---

`/home/yoshimi/WorkSpace/LLM-Manager` のPhase 6 Hardening / MVP Releaseを続けてください。
まず本ファイルを読み、必要な詳細だけ `docs/handoff-phase6.md` と下記検証記録で補ってください。
過去の時系列記録より本ファイルの再開位置を優先してください。

## 現在位置

- 2026-09-13最新: ff7913b Ubuntu local環境SBOMを採取・検証済み。1907 package、既存Brave関連2件のcopyright欠落、license reviewは未完了。artifact/hash/checksum/BOM整合性成功、snapshot復元後baseline完全一致、一時snapshot削除。詳細: `docs/validation/phase6-ff7913b-ubuntu-local-sbom-2026-09-13.md`。次はUbuntu remote／Debian local環境SBOM、Qt/license review、SSH残Gate。

- 2026-09-13最新: ff7913b Debian fresh/reinstall/remove/再fresh/purgeと英日Wayland AT-SPIを完了。label relation/用途/内部ID非露出と通常終了に成功。追加12件だけをpurgeしbaseline完全一致、deb削除、両VM running。詳細: `docs/validation/phase6-ff7913b-debian-2026-09-13.md`。次はSSH/SBOM残Gate。Debian旧版upgrade、menu再操作、Orca音声聴取は未完了。

- 2026-09-13最新: ff7913b由来local/remoteのUbuntu lifecycleは完了。両Gateでupgrade/reinstall/remove/fresh/purge成功、running復元後baseline完全一致、一時snapshot削除済み。localはUID1000 offscreen Qt起動/closeも成功。詳細: `docs/validation/phase6-ff7913b-ubuntu-lifecycle-2026-09-13.md`。次は同candidateのDebian/SSH/SBOM残Gate。

- Phase 0〜5完了、現在・次ともPhase 6。release versionは0.1.0、UNRELEASEDのまま。
- branch `main`。`8056850`以降のaccessibility修正、回帰test、検証証拠、本文書更新をまとめてcommit/pushする承認を取得済み。保存後のcommit IDと同期状態は `git log -1`、`git status -sb` で再取得する。
- 再開時に `git status --short` を確認し、利用者の変更を保持する。
- 前チャットは5時間枠の残り10%で停止。その後再開し、新candidate Debian検証も完了・cleanup済み。
- 本文からの再開後、新candidate remote helper lifecycleも完了・cleanup済み。詳細は下記。

## candidate状態（旧candidateと混用禁止）

2026-09-13更新: 現在の採用candidateはcommit `ff7913bb97e896f7992720b9a43c2382970a5fc8`
から両debを独立2回build/verifyしてbyte完全一致したセット。
保存先 `/tmp/llm-manager-candidate-ff7913b-20260913/`。

- local SHA-256: `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`
- remote SHA-256: `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d`
- 各build内806 test成功。localは下記overlay artifactと同一hashでAT-SPI証拠を関連付け可能。
- 次はこのセットのOS lifecycle/remote/SSH/SBOM残Gate。以下の再build予定は完了済み。
- 詳細: `docs/validation/phase6-candidate-rebuild-2026-09-13.md`。

commit `b15a98454ddf9e397333350d371b35cc2ed8fdd8`由来の次のcandidateは、
accessibility修正により現行sourceに対してobsolete。過去Gateの証拠として保持するが、
今後の採用candidateや最終artifactとして使わない。

保存先: `/tmp/llm-manager-candidate-b15a984-20260912/`

- `llm-manager_0.1.0_all.deb`
  - SHA-256: `292b831c5454e3a6d41b59a67145474a76b066146bebc4e7308b81a6e50ff7f8`
- `llm-manager-remote-helper_0.1.0_all.deb`
  - SHA-256: `ee4930896f02e72d7097c58878e8900bdb0c11a495b90fd3c7b6e14b0af034bc`

同commitのtracked sourceから独立2回build/verifyしbyte完全一致。
各build内806 test（767成功・39 expected skip）が成功。
旧 `/tmp/llm-manager-release-candidate-4722cfa/` も残るが、新candidateの検証根拠にはしない。

accessibility修正確認用local deb:

- `/tmp/llm-manager-accessibility-fix-20260912/llm-manager_0.1.0_all.deb`
- SHA-256: `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`
- basisはcommit `8056850`のtracked source、overlayは今回変更したsource/test 4ファイルだけ。
- 未コミットoverlay artifactなので採用candidateや再現可能buildの根拠にしない。
- 修正をcommit後、同一commitからlocal/remote両debを独立2回build/verifyする。

## 完了済み（再実行不要）

0. 長時間Agentのrelease Gateを60分連続＋GUI cancelと定義し、Ubuntu実Qtで完走。
   3600.116秒、最大event gap 66.258 ms、cancel回収53.625 ms、親RSS増加3,028 KiB、
   child peak 50,252 KiBで全15 check成功。guest `/tmp` cleanup後baseline完全一致。
   合成Agent相当負荷で、実モデル推論・network API・任意4時間soakではない。詳細:
   `docs/validation/phase6-long-running-agent-2026-09-13.md`。

0a. Ubuntu通常Wayland/system AT-SPIの英日accessibility Gate。旧b15a984 candidateで
    combo box用途とlabel relationの欠落、内部ID露出を検出して修正。修正版で
    `label_for`/`labelled_by`、用途description、focusable/enabled、内部ID非露出、
    Alt+F4通常終了が成功。Ubuntu system PySide6 focused 38件は37成功・1 expected skip。
    snapshot復元後baseline完全一致、一時snapshot削除済み。詳細:
    `docs/validation/phase6-accessibility-atspi-2026-09-12.md`。

1. 新candidate remote helperをUbuntu一時snapshot内で検証。旧`0.1.0~dev0`からのupgrade、
   reinstall、remove、fresh install、purge、readiness metadata、root owner/mode、private
   runtime、local GUI/PolicyKit非混入が成功。全境界で保全path不変、snapshot内cleanupと
   running復元後にpackage/manual/pathがbaseline完全一致。一時snapshotとupgrade用旧debは
   削除済み。詳細: `docs/validation/phase6-remote-helper-candidate-lifecycle-2026-09-12.md`。

2. 新candidate Debian 13のfresh install/reinstall/remove/再fresh install/purgeと実menu起動、
   UID 1000隔離argv、日英keyboard切替、通常終了を確認。固定12件だけを明示purgeし、
   package/manual/既存設定等はbaseline完全一致。転送deb削除済み、両VM running維持。
   詳細: `docs/validation/phase6-debian-candidate-display-2026-09-12.md`。

3. 新candidateのUbuntu 26.04 local lifecycle / 通常Wayland実display。
   upgrade/reinstall、GNOME menu起動、UID 1000隔離argv、日本語/英語keyboard切替、
   Alt+F4通常終了、remove/fresh install/purge、dpkg検査が成功。
   installed catalogにも旧「Sandbox」誤表記はない。
4. Ubuntu一時snapshotをrunningへ復元し、package/manual一覧と既存設定/SSH/root backupの
   owner/mode/hashが開始値と完全一致。一時snapshotとVMの検証debは不在。
5. 旧candidateで実OpenCode/dual backup/SSH GUI Apply・rollback・応答喪失後照合成功。
   ただしloopback SSH・Gate plan注入・応答喪失例外注入であり、物理回線断ではない。
6. 通常SSH診断5 sampleと実SSH待機cancel3 sampleを測定。
   診断中央値1614.899 ms。cancel→local SSH回収1.350〜1.429 ms。
   Qt/長時間Agent/Apply回線断の完了根拠ではない。

## VMの最終確認状態（再開時に再取得する）

- Ubuntu `ubuntu26.04`、Debian `debian13` はともにrunning。電源状態を維持する。
- Ubuntu IPは最後の確認で `192.168.122.48`、user `yoshimi` UID1000。
  Wayland session 3、Active=yes、State=active、LockedHint=no。
- Ubuntu既存snapshot `phase4-pre-local-deb-20260831` は保持。今回の一時snapshotは削除済み。
- Debianは検証後cleanup済み。user `user` UID1000、Wayland session 2で実画面確認済み。
  IP/ログイン/画面状態は再確認する。SSH serverがない場合はguest-agentで作業する。
- `guest-get-users` が空でもログイン不在と判定しない。loginctlと実画面で確認する。
- 通常system SSHは正常。sandbox内だけのowner表示を根拠にhost設定の修復を要求しない。
  必要なSSH/virsh操作は正式な権限昇格で行い、`-F /dev/null`で迂回しない。

## 次の作業

1. 新candidateのDebian 13 local lifecycle / 実displayは完了。旧版upgradeは未実施。
   以下は将来Debianを再検証する際の安全条件として保持する。
   開始package/manual集合とstateを保存し、APT simulationで追加packageを固定する。
   Debianの内部snapshotは以前pflash NVRAM形式で拒否されたため、NVRAMを変更せず、
   追加packageだけの明示purgeによるexact cleanupを基本とする。
   過去の「追加11依存」などを再確認なしに固定しない。autoremoveや既存依存の削除は禁止。
   先に復元方法を確定し、導入→検証→cleanup→開始値照合まで完了させる。
2. ff7913bからの両deb再現buildとUbuntu local/remote lifecycleは完了。
   Debian fresh/reinstall/remove/purgeと英日Wayland AT-SPIも完了。旧版upgradeは未実施。
3. 別マシン間SSH切断、SBOM/license等の残Gateへ進む。60分Agent Gateは完了済み。
   Ubuntuの一時snapshotを使う場合は、その時点の開始状態を保存・復元する。
4. `docs/release-checklist.md` の未完了項目を継続する。
   新candidate/最終artifactのSBOM、Orca音声人手聴取、署名等は未完了。
   最終artifactでの反復はUNRELEASED解除後にも必要。
   署名鍵は未指定。秘密鍵の自動生成・推測選択・署名/公開はしない。

## 読むべき記録・再利用できる実装

- `docs/validation/phase6-accessibility-atspi-2026-09-12.md`
- `docs/validation/accessibility-fix-2026-09-12/gate.py`
- `docs/validation/phase6-long-running-agent-2026-09-13.md`
- `docs/validation/long-running-agent-2026-09-12/gate.py`
- `docs/validation/phase6-candidate-rebuild-2026-09-12.md`
- `docs/validation/phase6-ubuntu-candidate-display-2026-09-12.md`
- `docs/validation/ubuntu-display-b15a984-2026-09-12/lifecycle.py`
- `docs/validation/phase6-debian-display-2026-09-10.md`（旧artifactの手順参考のみ）
- `docs/validation/phase6-0.1.0-debian-lifecycle-2026-09-09.md`
- `docs/validation/ssh-gui-2026-09-11/vm-lifecycle.py`（qga/転送/inventory関数を再利用可能）
- `docs/validation/phase6-ssh-gui-installed-2026-09-11.md`

証拠dir内のscriptは当時の固定path/hashを含む記録用であり、未変更で再実行しない。
新しいaction用scriptは `apply_patch` で作成し、対象・hash・復元条件を明示する。
VM操作の前後を短く報告し、秘密情報をチャットへ要求しない。
sub-agentは明示依頼がないため起動しない。
