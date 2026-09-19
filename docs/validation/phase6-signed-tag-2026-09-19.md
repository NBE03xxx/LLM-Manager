# Signed tag `v0.1.0`（2026-09-19）

## 結論

利用者の継続承認に基づき、release専用OpenPGP署名副鍵を完全指定してannotated tag `v0.1.0`を
作成した。tag targetは検証文書を含む最新HEADではなく、final artifactをbuildしたsource commit
`5b7d4de03e495fe630deab952de043f945a22bd7`へ固定した。

公開鍵だけをimportした隔離GPG homeで署名とfingerprintを検証後、tagだけを`origin`へpushした。
remoteのtag objectとpeeled targetがlocalと一致することを確認した。GitHub Releaseは作成しておらず、
artifactの公開と公開後再取得検証は未実施である。

## Tag identity

- tag: `v0.1.0`
- tag object: `e766d2041e83fedffb5fd3180aabadbc8696345e`
- object type: annotated tag
- tag object size: 372 bytes
- target commit: `5b7d4de03e495fe630deab952de043f945a22bd7`
- tagger: `NBE03xxx <NBE03247@nifty.com>`
- tag time: `2026-09-19T13:00:55Z`
- subject: `LLM Manager 0.1.0`

tag作成時点のvalidation HEADは`e8ab43ec57b22a77da69266e12835f2bfffcb47b`だった。このcommitを
誤ってtargetにせず、release setの正本であるbuild source commitを明示指定した。

## 署名と隔離検証

- primary fingerprint: `353F4D4F55175F537FBCD07C3E2532969B404FFD`
- signing subkey fingerprint: `034DA1601E14BE534254BA4DD8F253C086BE34C2`
- identity: `NBE03xxx <NBE03247@nifty.com>`

署名副鍵fingerprintへ`!`を付けて完全指定した。新しい一時GPG homeへrepositoryの
`RELEASE_KEY.asc`だけをimportし、primary／subkey fingerprintの完全一致と秘密鍵file 0件を確認した。
その環境で`git verify-tag --raw v0.1.0`を実行し、次のstatusを得た。

```text
GOODSIG D8F253C086BE34C2 NBE03xxx <NBE03247@nifty.com>
VALIDSIG 034DA1601E14BE534254BA4DD8F253C086BE34C2 2026-09-19 1789822855 0 4 0 22 10 00 353F4D4F55175F537FBCD07C3E2532969B404FFD
TRUST_UNDEFINED 0 pgp
```

`TRUST_UNDEFINED`はowner trust未設定の新規keyringなので期待どおりである。固定済みfingerprintと
`VALIDSIG`の完全一致を判定に使用した。import時に秘密鍵用gpg-agentの起動警告が出たが、公開鍵の
import／列挙とtag signature検証は成功しており、秘密鍵は隔離環境へコピーしていない。

## Remote検証

`git push origin refs/tags/v0.1.0`でtagだけをpushした。続くremote参照は次のとおり。

```text
e766d2041e83fedffb5fd3180aabadbc8696345e  refs/tags/v0.1.0
5b7d4de03e495fe630deab952de043f945a22bd7  refs/tags/v0.1.0^{}
```

tag objectはlocalと一致し、peeled targetはfinal artifact source commitと一致する。`gh release list`は
空であり、この操作ではGitHub Releaseを公開していない。

## 保存証拠

- `signed-tag-2026-09-19/tag-object.txt`: 署名を含むraw annotated tag content
- `signed-tag-2026-09-19/verification.json`: local／isolated GPG／remote照合結果
- `signed-tag-2026-09-19/EVIDENCE-SHA256SUMS`: 上記2fileのhash

この完了で公開checklistは43/44、97.7%。残件はGitHub Release公開後に全artifactを再取得し、
checksum、署名、package verifierを再実行する1項目である。
