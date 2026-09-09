# Phase 6 `0.1.0` Debian lifecycle Gate

## 結果

commit `4722cfa5238af507deee0831bdf8a0cbe517fe99`由来のlocal candidate
`llm-manager_0.1.0_all.deb`（SHA-256
`25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181`）をDebian
13で検証した。

package未導入状態からのfresh install、同一version reinstall、remove、再fresh install、purgeは
すべて成功した。`dpkg -V`、UID 1000の隔離Python import/offscreen Qt起動、installed fileの
owner/modeも成功した。開始時に存在しなかった依存11件とcandidateだけを明示purgeし、package
集合を開始値へ戻した。

これは`UNRELEASED` candidateのpre-final Gateである。active desktop sessionがなかったため
実display/menuは未実施で、開始時に旧版がなかったためupgradeも未実施。最終artifactのlifecycle
項目は未完了のままとする。

## 開始状態

- VM: `debian13`、shut off
- 起動後IP: `192.168.122.239`
- logged-in user: なし
- SSH server: 未導入、`ssh.service` inactive/unitなし
- `llm-manager`: 未導入
- package数: 2236
- sorted package set SHA-256:
  `d4b4d64a2dd5ca6436291fe1425aba368765ae8d63d26ea01251184da685d35e`
- `/tmp/llm-manager_0.1.0_all.deb`: なし

内部snapshot `phase6-0.1.0-lifecycle-20260909`の作成を試みたが、pflash firmwareのNVRAMが
QCOW2形式でないためlibvirtが変更前に拒否した。NVRAM形式を変更せず、開始package集合の採取と
追加packageの明示purgeによるexact-cleanup Gateへ切り替えた。snapshotは作成されていない。

OpenSSH serverを追加せず、candidateはQEMU guest agentのfile APIで`/tmp`へ転送した。転送直後
のroot:root 0666をinstall前にroot:root 0644へ固定し、host artifactとのSHA-256一致を確認した。

## APT差分

install前のAPT simulationで、新規導入対象をcandidateと次の依存11件に固定した。

- `libclang1-19 1:19.1.7-3+b1`
- `libpyside6-py3-6.8 6.8.2.1-4`
- `libshiboken6-py3-6.8 6.8.2.1-4`
- `python3-bcrypt 4.2.0-2.1+b1`
- `python3-cffi-backend 1.17.1-3`
- `python3-cryptography 43.0.0-3+deb13u1`
- `python3-jeepney 0.9.0-1`
- `python3-pyside6.qtcore 6.8.2.1-4`
- `python3-pyside6.qtgui 6.8.2.1-4`
- `python3-pyside6.qtwidgets 6.8.2.1-4`
- `python3-secretstorage 3.3.3-3`

simulationと実installはいずれも0 upgraded、12 newly installedだった。

## Lifecycle

1. package未導入状態からcandidateと依存11件をfresh installした。
2. `apt-get install --reinstall`で同じ`0.1.0`を再導入した。
3. `apt-get remove llm-manager`でpackage本体だけを削除した。全主要package-owned pathの不在と
   依存11件の保持を確認した。
4. candidate本体だけを再fresh installした。
5. candidate本体と開始時に存在しなかった依存11件を、固定したpackage名で一括purgeした。
   `autoremove`は使用していない。

fresh install状態では次を確認した。

- package version `0.1.0`、`dpkg -V`無出力
- UID 1000、`/usr/bin/python3 -I`で`llm_manager.__version__ == 0.1.0`
- Debian stock `PySide6 6.8.2.1`
- 5 launcherはroot:root 0755
- desktop/icon/helper metadata/notices/SBOMはroot:root 0644
- UID 1000、`QT_QPA_PLATFORM=offscreen`でGUIが5秒間継続しtimeout 124

GUI stderrは、書込み可能なFontconfig cacheがないという警告と既知のQt
`propagateSizeHints`警告だけだった。active desktop実displayの根拠には使用しない。

## Exact cleanup

candidateと依存11件を明示purgeし、転送した`.deb`を限定pathから削除した。全主要
package-owned pathの不在に加え、package数2236とsorted package set SHA-256の開始値完全一致を
確認した。`dpkg-query`のavailable metadataに`un`が残る場合があるため、導入有無はpackage集合と
`db:Status-Abbrev`で判定した。

SSH server、実設定、service、Secret Service、backup/key、利用者dataは変更していない。VMは
正常shutdownし、開始時どおりshut offへ戻した。

現在・次ともPhase 6。次はUbuntu local/remoteとDebian local candidateの
resolved-environment SBOM、Qt package license review、ログイン済みDebianでの実display/menuを
進める。`UNRELEASED`解除後は最終commitからartifactを再buildし、本Gateを最終artifactで再実行する。
