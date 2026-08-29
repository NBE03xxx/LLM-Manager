# ADR-0009: AES-256-GCMとLocal/Remote独立鍵を使う

- Status: Accepted
- Date: 2026-08-29

## Decision

Python `cryptography`のAES-256-GCMで16 MiB以下のbackup itemごとに暗号化する。local keyはSecret Service、remote keyはremote root-only key storeに置く。同じplaintextをcopyごとの独立鍵・nonceで暗号化し、canonical AADにbackup/host/targetを束縛する。

## Consequences

local PC喪失時もremote単独復元が可能で、どちらかの鍵喪失を他方で補える。remote root compromiseではremote keyとcopyの双方が露出し得る。envelope versioning、nonce uniqueness、key loss testが必要になる。
