# Remote Helper deb Lifecycle Validation — 2026-08-30

## Scope

Phase 4のdisposable SSH target `llm-manager-gate`（Ubuntu 26.04）で、最新sourceからbuild・artifact検証した`llm-manager-remote-helper` 0.1.0~dev0を同一版reinstall、remove、purge、再installした。管理者認証は外部端末だけで行い、passwordをアプリ、argv、stdin、logへ渡していない。

artifact SHA-256は`2ecd6ef2076a4b9233fdbec6e93eba9d31993e78124c28d0116fd5776be4683a`、private runtime `remote_helper.py` SHA-256は`c0cff8a0cc5f369971414e2ddab350fef7a6fb599d0173266284674e361a8f3f`である。

## Result

| Stage | Package/helper | Compatibility | Root backup/key |
|---|---|---|---|
| 同一版reinstall | 0.1.0~dev0、最新runtime hash一致 | `ready` | 保持 |
| remove | package/helper不在 | `missing` / `helper_not_installed` | 保持 |
| purge | `not-installed`、helper不在 | fail closedのまま | 保持 |
| 再install | 0.1.0~dev0 | `ready` | 保持 |

再install後のmetadataはhelper `root:root 0755`、metadata/private runtime `root:root 0644`で、protocol version 1、`root_apply_allowed=true`をproduction adapterで確認した。

packageにmaintainer scriptとconffileはなく、`/var/lib/llm-manager/backups`と`/var/lib/llm-manager/keys`はdpkg管理対象外である。このためremove/purgeは復旧copyとkeyを自動削除しない。purge時点ではremoveにより既に`not-installed`で、残存conffileはなかった。最後にhelperを再installし、次のGateを実行可能な状態へ戻した。

## Remaining Gate

Debian 13で同じlifecycle差異を確認する。local `llm-manager` debのinstall/upgrade/remove/purgeとPolicyKit desktop認証は別Gateである。
