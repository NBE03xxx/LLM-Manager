# Phase 6 release signing key validation (2026-09-15)

## Outcome

利用者がrelease専用OpenPGP主鍵と署名副鍵を作成し、試験署名を検証して期待結果を確認した。
公開情報だけをlocal GnuPG keyringから再確認し、公開鍵を`RELEASE_KEY.asc`へ収録した。
秘密鍵、passphrase、失効証明書、試験署名fileは読み取らず、repositoryにも収録しない。

release keyの保管責任者は`Project owner (NBE03xxx)`。特定の後継者は指定せず、活動中だけ
署名副鍵を更新する。長期離脱または死亡時は最長1年で署名副鍵を期限切れとし、継続希望者は
独立したforkと自分の署名鍵を用いる。

## Public identity

- UID: `NBE03xxx <NBE03247@nifty.com>`
- primary algorithm/capability: Ed25519 / certification
- primary fingerprint: `353F4D4F55175F537FBCD07C3E2532969B404FFD`
- primary created: `2026-09-15T22:40:16+09:00`
- primary expires: `2031-09-14T22:40:16+09:00`
- signing subkey algorithm/capability: Ed25519 / signing
- signing subkey fingerprint: `034DA1601E14BE534254BA4DD8F253C086BE34C2`
- signing subkey created: `2026-09-15T22:46:23+09:00`
- signing subkey expires: `2027-09-15T22:46:23+09:00`
- custodian: `Project owner (NBE03xxx)`
- successor: none designated

完全fingerprintをrelease notes、`SHA256SUMS`署名検証手順、signed tag検証へ使用する。
短いkey ID `3E2532969B404FFD`または`D8F253C086BE34C2`だけでは鍵を選ばない。

## Repository boundary

確認時のworktreeにはrelease key関連の未追跡fileがなく、失効証明書、秘密鍵export、
`test-SHA256SUMS`もなかった。誤追加を防ぐため、想定するroot-level秘密file名と試験file名を
`.gitignore`へ追加した。公開鍵だけを`RELEASE_KEY.asc`へ追加する。

公開鍵収録後に、export済みpublic keyとrepository fileのpacket/fingerprint同一性、
OpenPGP parse、秘密packet不在を検証する。GitHub accountへの公開鍵登録とImmutable Release設定は
外部状態であり、この記録だけでは完了扱いにしない。

## Remaining release work

- `debian/changelog`はrelease日時確定まで`UNRELEASED`を維持する。
- release時に署名副鍵の有効期限が十分残っていることを確認する。
- final `SHA256SUMS`をASCII-armored detached signatureで署名し、別環境で主鍵fingerprintを
  指定して検証する。
- 同じ鍵でrelease tagを署名し、tagがfinal source commitを指すことを検証する。
- GitHub Release公開後、公開assetを再取得して署名、checksum、artifact verifierを再実行する。
