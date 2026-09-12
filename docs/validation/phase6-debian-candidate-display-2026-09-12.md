# Phase 6: updated candidate Debian lifecycle / desktop

## 結果

source `b15a98454ddf9e397333350d371b35cc2ed8fdd8` 由来の
`llm-manager_0.1.0_all.deb` をDebian 13の通常Wayland desktopで検証した。
SHA-256: `292b831c5454e3a6d41b59a67145474a76b066146bebc4e7308b81a6e50ff7f8`。
ホスト原本とguest転送後のhashを照合している。

- fresh install、reinstall、remove、再fresh install、purgeに成功。
- GNOMEで `llm` を検索し、Enterによる通常menu起動に成功。
  PID 3683、全UID 1000、argv `/usr/bin/python3 -I /usr/bin/llm-manager`。
- 日本語Hosts画面、Tabによるhost/language focus、Upによる英語切替を実画面で確認。
  `keyboard-host-focus.png` は英語切替前の日本語画面、`english.png` が切替完了の証拠。
- Alt+F4通常終了後、対象processのpgrep exit 1を確認。
- `dpkg -V llm-manager` 無出力、一般userのPython `-I` import成功。
  installed catalogにも旧「Sandbox」誤表記がない。

## 復元と証拠

[証拠directory](debian-display-b15a984-2026-09-12/)へscript、APT gzip log、
package/manual inventory、既存設定等のowner/mode/hash、実画面、checksumを保存した。
APT simulationでcandidateと新規依存の計12件を固定し、既存packageの更新・削除がないことを確認。
snapshot/NVRAMには触れず、終了時は固定12件のみのpurge simulationを確認して明示purgeした。
`autoremove` は使用していない。

導入後の最初の照合では、APTの `python3-cffi-backend` とdpkgの
`python3-cffi-backend:amd64` の表記差により検証scriptのassertionが停止した。
保存済みinventoryから追加対象12件だけであることと既存package不変を確認し、
名前比較でarchitecture suffixを扱うよう修正して再検証した。製品側の不具合ではない。
保存inventory自体のpackage名・version・statusは正規化せず保持している。

最終 `baseline.json` と `cleaned.json` はpackage全件・APT manual一覧・監視対象pathを含め完全一致。
監視対象は `/home/user/.config/llm-manager`、`/home/user/.config/opencode`、
`/home/user/.ssh`、`/var/lib/llm-manager`、`/usr/local/bin/opencode`。
`dpkg --audit` は無出力、`apt-get check` 成功。
guestの転送deb `/tmp/llm-manager-b15a984-20260912.deb` は削除済み。
両VMはrunningを維持し、Ubuntuは電源状態の読取りのみで変更していない。

## 範囲と残件

これはUNRELEASED candidateの検証で、最終release Gate完了ではない。
Debian旧版からのupgrade、新candidateのremote helper/SSH等の残Gate、
最終artifactでの再実行、screen reader、長時間Agent、SBOM/license review、署名が残る。
製品sourceに変更はなく、806件のbuild内testは再実行していない。
現在・次ともPhase 6。公開・push・署名は行っていない。
