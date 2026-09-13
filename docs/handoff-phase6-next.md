# 次チャット用引継ぎ（2026-09-13）

`/home/yoshimi/WorkSpace/LLM-Manager` のPhase 6 Hardening / MVP Releaseを続けてください。
まず本ファイルを読み、必要な詳細だけ `docs/handoff-phase6.md` と検証記録で補ってください。
本ファイルを過去の時系列記録より優先してください。

## 現在位置とGit

- Phase 0〜5完了。現在・次ともPhase 6。version 0.1.0、UNRELEASEDを維持。
- branch `main`。最新commit/remote/worktree状態は再開時に取得する。
- 本文書更新は別commitになるため、再開時は `git status -sb` と `git log -5 --oneline` を取得する。
- ユーザーは「検査後にまとめてコミット・プッシュ」を承認済み。各検証sliceをその方針で保存してきた。
- `ff7913b`以降は検証script・証拠・文書のみ変更。製品source変更なし。
- 実行中Gate、認証待ち、未復元snapshotはない。net2の実NIC断commit照合に成功。
  net/net2とr2/r3はすべて両VM cleanup完了。最後にsystem clockを補正済み。
  初回netは監視前にApplyが完了し、stale markerチェックによりNIC切断を中止。
  非採用証拠を保存して両VM cleanup済み。net2は新しいoperationであり再送ではない。
  r2は時計ずれの拒否を再現、時計補正後の新規r3でrollback成功。
  snapshot復元後も両VMの時計を明示承認に基づき補正済み。NTP設定は未変更。
  以前のcross-vm Gateと60分試験もcleanup済み。

## 進捗の表示方針

ユーザーは今後の報告に進捗率の%表示を希望している。
再開時にrelease checklistのトップレベルcheckboxを集計し、分母を明記する。
2026-09-13現在は18/44件、**40.9%（公開チェックリスト項目数ベース）**。
Phase 0〜5を含む全開発工数の割合や残り時間を意味しない。
以前報告した「技術検証約89%／公開準備約62%」は重み付けを定義していない概算であり、
この40.9%とは比較しない。今後は再集計可能な値を主表示とする。
部分検証が増えてもcheckboxの完了条件を満たさない限り数値は上げない。

## 採用candidate

source commit: `ff7913bb97e896f7992720b9a43c2382970a5fc8`

保存先: `/tmp/llm-manager-candidate-ff7913b-20260913/`

| artifact | SHA-256 |
| --- | --- |
| `llm-manager_0.1.0_all.deb` | `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243` |
| `llm-manager-remote-helper_0.1.0_all.deb` | `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d` |

引継ぎ更新時に両hashを再確認済み。再開時も存在/hashを確認する。
tracked sourceから両debを独立2回build/verifyしbyte完全一致。
各local build内806 test（767成功・39 expected skip）、ELF/shared library/bytecode混入なし。
localはaccessibility修正確認用overlay artifactと同じhashで、そのAT-SPI証拠を関連付け可能。
旧b15a984/4722cfaセットは過去証拠用。現candidateの検証済み根拠として混用しない。
詳細: `docs/validation/phase6-candidate-rebuild-2026-09-13.md`。

## 完了済み

1. **Ubuntu local/remote lifecycle**: 新candidate両debのupgrade/reinstall/remove/fresh/purge成功。
   local UID1000 isolated importとoffscreen Qt起動/close、remote metadata/owner/mode/private
   runtime/local GUI非混入を確認。各snapshot復元後baseline完全一致、一時snapshot削除済み。
   記録: `docs/validation/phase6-ff7913b-ubuntu-lifecycle-2026-09-13.md`。
2. **Debian lifecycle/AT-SPI**: 新candidateのfresh/reinstall/remove/再fresh/purge、英日Wayland
   installed launcher起動、用途/label relation/focusable/内部ID非露出、Alt+F4 exit 0成功。
   追加12件のみpurgeしbaseline完全一致、deb削除。このlifecycle sliceでは旧版upgrade、menu再操作、
   Orca音声を未実施だったが、後続の上記9〜11で検証・capture済み（人のWAV聴取のみ待ち）。
   記録: `docs/validation/phase6-ff7913b-debian-2026-09-13.md`。
3. **Ubuntu accessibility**: combo box用途欠落・内部ID露出を修正し英日AT-SPI成功。
   system PySide6 focused 38件（37成功・1 expected skip）。
   記録: `docs/validation/phase6-accessibility-atspi-2026-09-12.md`。
4. **60分Agent Gate**: 3600.116秒、全15 check成功。最大event gap 66.258 ms、cancel回収
   53.625 ms、親RSS増加3,028 KiB。child reap、worker inactive、watchdog不使用。
   合成Agent相当workload。モデル推論/network APIは含まない。4時間soakは任意。
   記録: `docs/validation/phase6-long-running-agent-2026-09-13.md`。
5. **Ubuntu local環境SBOM**: 新candidate installed環境1907 packageを採取。artifact hash、
   内外checksum、TSV/inventory/BOM整合性成功。copyright欠落は既存Brave関連2件。
   collector exit 2、license review完了判定false。snapshot復元後baseline完全一致。
   記録: `docs/validation/phase6-ff7913b-ubuntu-local-sbom-2026-09-13.md`。
6. **Ubuntu remote helper環境SBOM**: 新candidateをfresh installし1908 packageを採取。
   APT追加はhelper 1件のみ。artifact hash、内外checksum、TSV/inventory/BOM整合性成功。
   copyright欠落は既存Brave関連2件、collector exit 2、license review完了判定false。
   snapshot復元後baseline完全一致、一時snapshot削除済み。
   記録: `docs/validation/phase6-ff7913b-ubuntu-remote-sbom-2026-09-13.md`。
7. **Debian local環境SBOM**: 今回のAPT simulationでcandidate＋新規依存11件を固定し、
   fresh install環境2248 packageを採取。copyright欠落なし、collector exit 0。
   artifact hash、内外checksum、TSV/inventory/BOM整合性成功。12件だけを明示purgeし、
   baseline完全一致、audit/check成功。VMとWayland sessionはrunning/activeを維持。
   記録: `docs/validation/phase6-ff7913b-debian-local-sbom-2026-09-13.md`。
8. **Qt/PySide6 license review**: 3環境の現archiveから各25 binary・6 source系統を比較。
   選択packageのcopyright欠落なし。Ubuntu local/remoteのmetadata/原文hash一致、両OSの
   PySide6主Files節とQt GPL Exception本文、QtBase主Files節、追加license名を確認。
   直接依存SBOMは主選択肢の要約として整合。法的適合の自動完了とは扱わない。
   記録: `docs/validation/phase6-ff7913b-qt-license-review-2026-09-13.md`。
9. **Debian旧版upgrade**: commit 8854232のtracked sourceからbuild・historical verifier済みの
   `0.1.0~dev0`をfresh installし、新candidate `0.1.0`へupgrade。simulation/実行とも変更は
   `llm-manager` 1件だけ。dpkg検証、UID1000 isolated import/offscreen Qt成功。
   固定12件だけをpurgeしbaseline完全一致、Wayland sessionを維持。
   記録: `docs/validation/phase6-ff7913b-debian-upgrade-2026-09-13.md`。
10. **Debian menu再検査**: GNOME overviewで`llm`検索し、icon/名称を画像確認。Enterで
    日本語UIを起動し、UID1000と固定argv、Alt+F4通常終了を確認。固定12件だけをpurgeし
    baseline/session完全一致、VM running。画像を含むmanifest全件一致。
    記録: `docs/validation/phase6-ff7913b-debian-menu-2026-09-13.md`。
11. **Debian Orca音声capture**: 一時prefsでOrcaを起動し、製品名、Hosts用途/valueを含む
    12発話eventと20.672秒の非無音WAVを保存。app exit 0、toolkit accessibility false復元、
    固定12件purge後baseline/session完全一致。人によるWAV聴取確認は未完了。
    記録: `docs/validation/phase6-ff7913b-debian-orca-2026-09-13.md`。
12. **別VM間SSH正常Apply（部分Gate）**: ff7913b Debian GUI→Ubuntu remote helperで
    実OpenCode/dual backup/commit、応答喪失例外注入後のimmutable result照合成功。
    Apply 1回、Results可視。rollback予定caseはsudo認証待ちでApply前に停止し未検証。
    再送なし、設定hash維持、両VM復元済み。
    記録: `docs/validation/phase6-cross-vm-ssh-2026-09-13.md`。
13. **別VM間SSH rollback（部分Gate）**: r2でsudo認証後の時刻ずれ拒否を特定。
    両VM時計を補正した新規r3で、不正JSON→自動rollback成功。
    Apply/rollback各1回、例外注入後のimmutable result照合、元hashとResults表示を確認。
    両VMのpackage/manual/保全path/session復元済み。
    記録: `docs/validation/phase6-cross-vm-rollback-2026-09-13.md`。
14. **実NIC断後のSSH commit照合（部分Gate）**: net2でhelper成功後のstdoutを
    試験relayで保留し、Ubuntu live NICを4.020秒切断。SSH自身がexit 255、
    復旧後のimmutable result読み取り1回でcommitted。Apply 1回、例外注入なし。
    両VM復元済み。記録: `docs/validation/phase6-cross-vm-network-2026-09-13.md`。

旧candidateの実OpenCode/dual backup/SSH GUI Apply・rollback・応答喪失後照合も成功済みだが、
loopback SSH・Gate plan/例外注入を含み、別マシン間の物理切断ではない。
通常SSH診断5 sampleと実SSH待機cancel3 sampleも限定baselineとして保持する。
2026-09-13にはhost→Ubuntuの仮想NICを実際にdownにした状態でキャンセルを検証。
回収32.031 ms、link up復元、新しいstrict SSH接続とremote有限process不在を確認した。
詳細: `docs/validation/phase6-ssh-link-cut-2026-09-13.md`。Qt/Apply完了の代替ではない。

## 次の作業（この順を基本とする）

1. 保存したDebian Orca WAVを人が聴取し、発音・順序・聞き取りやすさを確認する。
2. `docs/release-checklist.md` のSSH機能/別マシン間切断、最終artifactのSBOM/lifecycle等を
   継続する。
   利用者はDebian画面でUbuntuのsudo認証が可能と回答済み。
   Debian GUI→Ubuntu SSHの正常Applyとrollbackは別caseで成功済み。
   実NIC断後の正常Apply照合もnet2で成功済み。次はrollback応答中の実通信断、
   通常GUI操作全経路などの残条件を絞り込む。最終artifact項目は未完了のまま。
   net2は成功応答を10秒保留するrelayと短いSSH keepaliveの限定caseである。
   次回ネットワークGateは必ずGUI launchより先にwatch readyを確認する。
   snapshot操作後は両VM時計を確認すること。r2で約200秒先のrequestを拒否した。
   手動Run Applyで入力タイミングを合わせる。保存済みoperationは再送しない。
3. 最終Gate後にUNRELEASED解除を判断。署名鍵は未指定。秘密鍵を自動生成・推測選択しない。
   release署名・tag・公開の承認を、通常のcommit/push承認と同一視しない。

## VMと復元条件

- 最後の確認ではUbuntu `ubuntu26.04`、Debian `debian13` ともrunning。電源状態を維持する。
- Ubuntu user `yoshimi` UID1000、最後のIP `192.168.122.48`、Wayland session 3。
- Debian user `user` UID1000、Wayland session 2。現在IP/session/lock状態は再取得する。
- Ubuntu既存snapshot `phase4-pre-local-deb-20260831` は保持。一時Phase 6 snapshotは削除済み。
- package/manual/保全pathは各Gate開始値へ復元済み。ホストのcandidate・一時build treeは保持。
- `guest-get-users`空だけでログイン不在と判定しない。loginctl/Wayland状態を確認する。
- 通常system SSHは復旧確認済み。sandbox内owner表示だけを根拠に修復を要求しない。
  sandbox拒否時は正式に権限昇格し、`-F /dev/null`で迂回しない。

## 再利用できる入口

- `docs/validation/collect-ff7913b-ubuntu-sbom-2026-09-13.py`：今回のUbuntu local SBOM採取。
- `docs/validation/sbom-ff7913b-ubuntu-local-2026-09-13/`：archive/verifier/APT/baseline/restored。
- `docs/validation/collect-ff7913b-ubuntu-remote-sbom-2026-09-13.py`：今回のUbuntu remote SBOM採取。
- `docs/validation/sbom-ff7913b-ubuntu-remote-2026-09-13/`：remote archive/verifier/APT/baseline/restored。
- `docs/validation/collect-ff7913b-debian-sbom-2026-09-13.py`：今回のDebian local SBOM採取/cleanup。
- `docs/validation/sbom-ff7913b-debian-local-2026-09-13/`：Debian archive/verifier/APT/baseline/cleaned。
- `docs/validation/review-ff7913b-qt-licenses-2026-09-13.py`：現archiveのQt/PySide6比較。
- `docs/validation/qt-license-review-ff7913b-2026-09-13.json`：package/source/license/hash結果。
- `docs/validation/debian-upgrade-ff7913b-2026-09-13.py`：Debian旧版upgrade/cleanup Gate。
- `docs/validation/debian-upgrade-ff7913b-2026-09-13/`：upgrade simulation/log/inventory/cleanup。
- `docs/validation/debian-menu-ff7913b-2026-09-13.py`：Debian menu導入/process/cleanup Gate。
- `docs/validation/debian-menu-ff7913b-2026-09-13/`：menu画像/process/APT/inventory/cleanup。
- `docs/validation/debian-orca-ff7913b-2026-09-13.py`：Orca/PipeWire captureとcleanup Gate。
- `docs/validation/debian-orca-ff7913b-2026-09-13/`：WAV/debug/発話/画像/APT/inventory。
- `packaging/collect-installed-sbom.py`、`packaging/verify-environment-evidence.py`：採取・archive検証。
- `docs/validation/phase6-0.1.0-candidate-environment-sbom-qt-2026-09-09.md`：旧候補のQt原文review参考。
- `docs/validation/lifecycle-ff7913b-2026-09-13.py`：Ubuntu local/remote lifecycle。
- `docs/validation/debian-ff7913b-2026-09-13.py`：Debian lifecycle/英日AT-SPI。
- `docs/validation/ssh-gui-2026-09-11/vm-lifecycle.py`：QGA実行/転送共通関数。
- `docs/validation/phase6-ssh-gui-installed-2026-09-11.md`：旧候補の限定SSH GUI証拠。

証拠scriptは固定path/hashと実行時stateを含む。新規Gateは別script/outputへ作成する。
QEMU guest-execの完了結果は一度読むと消費されるため、最初の完了pollで保存する。
GUI全体をrootで起動しない。SSH mutationを自動再送しない。利用者の秘密情報を要求しない。
sub-agentは明示依頼がないため起動しない。
