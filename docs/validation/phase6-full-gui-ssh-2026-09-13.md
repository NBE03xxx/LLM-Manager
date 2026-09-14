# ff7913b 通常GUIによる別VM間SSH Apply — 2026-09-13

Debianの通常ユーザーがHosts→Diagnose→Recommendations→Review Changes→
Apply / Resultsを操作し、UbuntuのOpenCode設定変更をcommittedまで完了した。
OpenCode存在・config parse検証はpassed、GUIの結果表示とguest exit 0を確認。
plan、approval、transportの試験注入はない。

## 構成と結果

現candidate ff7913bのlocal deb SHA-256は
`351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243`、
remote helperは`830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d`。
製品の通常起動関数`qt_app.main`をinstalled moduleから呼んだ。
MainWindowの観測用subclassが100 msごとに状態変化と画像を保存し、終端結果でcloseする。
UI状態・plan・approvalを設定せず、すべて利用者が表示controlを操作した。
これは通常compositionの検証であり、desktop launcher/menu自体の試験は別記録を参照する。

初期基準OpenCode 1.18.25は[公式release](https://github.com/anomalyco/opencode/releases/tag/v1.18.25)
の`opencode-linux-x64.tar.gz`を取得。GitHub API公表digestと実ファイルのSHA-256
`58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78`が一致した。
前の通信断Gateで使った1.18.30は通常rule/plannerの変更許可対象ではないため、
今回の通常推奨生成の証拠と混用しない。

対象は試験snapshot内の`/home/yoshimi/.config/opencode/opencode.jsonc`、
user所有0600。初期内容は次の1行と末尾改行。

```json
{"autoupdate": false, "compaction": {"auto": false, "prune": false}}
```

Agent profileが2件のactionable推奨を生成。利用者が両方を選択し、
`Approve reviewed changes`→`Prepare Apply`→`Run Apply`とsudo認証を行った。
最終configはautoupdate=falseを保ち、compaction.auto/pruneがともにtrue。

| 証拠 | 値 |
| --- | --- |
| operation | ssh-user-fbd8a3e468554a9f9ee4b512dedfed21 |
| journal状態 | committed |
| before SHA-256 | fcbdf78f1ce1c2bb87446df5f5fc64d9b6da5fd23824881109581152bfee98a7 |
| after SHA-256 | 682128216e9141bd32169fd999804f3992827cbc902aaf6d4057fd4eecdac0ea |
| local manifest | complete=true、AES-256-GCM |
| remote recovery receipt | verified=true、manifest/plan/change-set/before hash対応 |
| 画面状態履歴 | 20件 |

操作中、未診断のままRecommendationsを開くと説明なく空欄になることが観測された。
案内の「false → true」もボタン名と紛らわしかったため、実画面に合わせて
checkboxとボタン名を明示して完了した。UIの未診断表示改善は今後の候補であり未実装。
Wayland textinputのleave警告がstderrにあるが、操作・保存・正常終了は成功した。

## 証拠と復元

`full-gui-ssh-2026-09-13.py`と同名directoryへ画像、履歴、結果、journal/manifest/receipt、
APTとbaselineを保存した。XDG config/state/cacheは専用試験directoryへ分離。
Secret Serviceの`local-master-v1`参照が開始時に不在であることを確認して使用した。
終了後に今回作成した参照・SSH key/alias・試験directoryを削除し、Debianの追加12 packageを
明示purgeした。Ubuntuはsnapshotへ復元しbaseline一致後に一時snapshotを削除した。
両VMはrunning、package/manual/保全path/sessionは開始値と完全一致。
両VMの時計はsnapshot復元後に再同期済み。NTP設定は変更していない。

回帰806件（767成功・39 expected skip）、証拠checksum全件、GUI履歴と
journal/manifest/receiptの対応、変更後config、script構文、Git空白検査に成功。

この正常Apply経路は1 sample。通常GUIからのrollback/通信断の組合せ、local user/root
restore全操作、最終release artifact検証、性能全条件の完了を意味しない。
公開チェックリストは18/44件（40.9%）を維持する。
