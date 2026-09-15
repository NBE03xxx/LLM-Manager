# Phase 6 authentication context UI improvement（2026-09-14）

## 目的

外部ターミナルまたはPolicyKitダイアログで認証を求められたとき、利用者が
ローカルマシンの管理者認証かリモート接続先の認証かを表示だけで区別できるようにする。

## 実装

| 認証境界 | 表示 |
|---|---|
| OpenSSH ControlMaster接続 | `LLM-Manager — REMOTE SSH login — <user@host または alias>` |
| SSH先の対話`sudo` | `LLM-Manager — REMOTE sudo — <alias>` |
| local ApplyのPolicyKit | descriptionとmessageに`LOCAL`および`this computer`を明記 |
| local root restore review/executeのPolicyKit | descriptionとmessageに`LOCAL`および`this computer`を明記 |

SSH接続先は既存の構文検証を通過したtargetまたはaliasだけをタイトルへ渡す。
SSH、`sudo`、`pkexec`の固定argv、ControlMaster、helper protocol、timeout、再送規則は変更していない。
passwordをアプリ、タイトル、argvへ渡す経路も追加していない。

## 自動検証

- 対象38 test成功。SSH接続とremote sudoのタイトル、3つのPolicyKit actionの
  `LOCAL`表示、既存の固定argv・option injection拒否・秘密情報非混入を検査した。
- 全806 test成功（767成功、PySide6未導入による39 expected skip）。
- `compileall`、PolicyKit XML parse、両package verifier shell構文、desktop-file、
  両SBOM JSON、`git diff --check`成功。
- 作業ツリーの一時copyからlocal/remote debをbuildし、両deb verifier成功。展開した
  local package内で3つの`LOCAL` PolicyKit文言と2つの`REMOTE`タイトルを確認した。
  remote package内にも同じPython sourceが収録されていることを確認した。一時artifactは
  commit由来のcandidateではないため採用せず、検査後に削除した。

## artifactと残Gate

このsource変更より前の`ff7913b` candidateと、そのinstalled OS evidenceは履歴として有効だが、
本UI改善を収録していない。本変更を含む同一commitからlocal/remote candidateを再buildし、
Debian通常desktopで外部ターミナルタイトルとPolicyKit文言を目視するGateは未実施。
したがってfinal artifact項目は完了にせず、release checklistは18/44（40.9%）を維持する。

2026-09-15追記: commit `7f846f5`からcandidateを独立2回buildしてbyte一致を確認し、
[installed UI Gate](phase6-auth-context-ui-installed-2026-09-15.md)でremote sudoタイトルとlocal PolicyKit
messageを通常Debian desktop上に表示・保存した。final artifact項目と進捗は引き続き変更しない。
