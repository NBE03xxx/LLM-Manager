# 次チャット用引継ぎ（2026-09-13）

`/home/yoshimi/WorkSpace/LLM-Manager` のPhase 6 Hardening / MVP Releaseを続けてください。
まず本ファイルを読み、必要な詳細だけ `docs/handoff-phase6.md` と検証記録で補ってください。
本ファイルを過去の時系列記録より優先してください。

## 現在位置とGit

- Phase 0〜5完了。現在・次ともPhase 6。version 0.1.0、UNRELEASEDを維持。
- branch `main`。本引継ぎ更新前のHEAD/remoteは `9877e0a0b6db3cc4f79099d6784558a29e9aeb08`、worktree clean。
- 本文書更新は別commitになるため、再開時は `git status -sb` と `git log -5 --oneline` を取得する。
- ユーザーは「検査後にまとめてコミット・プッシュ」を承認済み。各検証sliceをその方針で保存してきた。
- `ff7913b`以降は検証script・証拠・文書のみ変更。製品source変更なし。
- 実行中Gate、回収待ちprocess、未復元snapshotはない。60分試験も終了・回収・cleanup済み。

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
   追加12件のみpurgeしbaseline完全一致、deb削除。旧版upgrade、今回のmenu再操作・画像目視・
   Orca音声聴取は未実施。記録: `docs/validation/phase6-ff7913b-debian-2026-09-13.md`。
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

旧candidateの実OpenCode/dual backup/SSH GUI Apply・rollback・応答喪失後照合も成功済みだが、
loopback SSH・Gate plan/例外注入を含み、別マシン間の物理切断ではない。
通常SSH診断5 sampleと実SSH待機cancel3 sampleも限定baselineとして保持する。

## 次の作業（この順を基本とする）

1. `docs/release-checklist.md` のSSH機能/別マシン間切断、Debian menu再検査、Orca音声、
   最終artifactのSBOM/lifecycle等を継続する。
2. 最終Gate後にUNRELEASED解除を判断。署名鍵は未指定。秘密鍵を自動生成・推測選択しない。
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
