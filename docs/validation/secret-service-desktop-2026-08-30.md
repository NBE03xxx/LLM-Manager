# Secret Service Desktop Validation — 2026-08-30

## Scope

Phase 4のlocal backup暗号鍵providerについて、GNOME desktop sessionでSecret Service production backendを利用できる前提をread-onlyで確認した。既存itemの検索、secret値の読込、一時itemの作成・削除は行っていない。Ollama、OpenCode、systemd、SSH先も変更していない。

## Environment and result

| Item | Observed result |
|---|---|
| Desktop/session | GNOME、Wayland |
| Session bus | `DBUS_SESSION_BUS_ADDRESS`あり |
| Keyring daemon | `/usr/bin/gnome-keyring-daemon`あり |
| `secret-tool` | 未導入 |
| Python `secretstorage` binding | source checkoutのsystem Python環境では未導入 |
| Backend result | `ModuleNotFoundError`。application境界ではstable `secret_service_unavailable`へ変換 |
| Secret mutation | なし |

## Assessment

これはavailabilityのnegative Gateである。一般配布向けdebは`python3-secretstorage (>= 3.5)`を依存関係として宣言済みだが、現在のsource checkout実行環境にはbindingがない。制約に従い仮想環境作成や`pip install`は行わなかった。

暗号化をsilentにOFFへ落とさず、Backup/Applyを停止できる境界は確認できた。default collectionへのcreate/reloadとlocked collectionのOS promptを含むpositive desktop Gateは、deb実install後のdesktop検証まで未完了とする。
