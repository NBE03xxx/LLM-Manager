# Local deb and Desktop Positive Validation — 2026-08-31

## Scope

Phase 4のdisposable Ubuntu 26.04 desktop VMで、local `llm-manager` debのinstall、同一版reinstall、remove、purge相当、reinstall、upgradeを実行した。あわせてSecret ServiceのGate専用key create/reload/delete、PolicyKitの認証成功・dismiss・deny、Gate専用path/unitだけを使うsystemd操作を確認した。開始前にlibvirt snapshot `phase4-pre-local-deb-20260831`を作成した。

main workstation、Ollama、OpenCode、SSH設定は変更していない。passwordはVMのdesktop promptまたはterminalだけで扱い、application、argv、stdin、logへ渡していない。

## Packaging defect and correction

初回artifactは`policykit-1`へ依存していたため、Ubuntu 26.04のAPT solverがcandidateなしでinstallを拒否した。VMのrepositoryは`resolute`のmain/restricted/universe/multiverseが有効で、`polkitd` 127-2ubuntu1、`pkexec` 127-2ubuntu1は導入済み、`python3-secretstorage` 3.5.0-1はcandidateありだった。

Ubuntu 26.04とDebian 13のpackage分割に合わせ、local packageは`polkitd`と`pkexec`へ個別依存するよう修正した。remote helper packageは両dependencyを含まないこともartifact verifierで検査する。

修正artifact `llm-manager_0.1.0~dev0_all.deb`のSHA-256は`8009d0c0af16ee587f2014d748b7608f1b70e06565506ded97b209c108a399f8`である。upgrade確認用に同じsourceからDebian revisionだけを変更した`0.1.0~dev0-1`をbuildし、SHA-256 `646f6eaa1e5ea339b2ef78e9501eb43db23f4617ba0ffa3ea24032edd38651cc`を検証した。

## Lifecycle result

| Stage | Result |
|---|---|
| install | `0.1.0~dev0`成功。`python3-jeepney` 0.9.0-2と`python3-secretstorage` 3.5.0-1を導入 |
| same-version reinstall | 成功。追加・削除なし |
| remove | helper/action/package filesを削除。`python3-secretstorage`、`polkitd`、`pkexec`は保持 |
| purge | conffile/maintainer scriptがないためremove時点でdpkg entryなし。query exit 1、追加削除対象なし |
| reinstall | `0.1.0~dev0`へ復帰 |
| upgrade | `0.1.0~dev0-1`へ成功。helper 0755、metadata/action 0644、root:rootとaction登録を維持 |

## Secret Service positive Gate

installed system Pythonと`SecretStorageBackend`を使い、default collectionへGate専用reference `phase4-desktop-gate-20260831`の32-byte keyを作成した。別backend/provider instanceから同じkeyを再読込後、該当itemを削除し、検索結果が0件であることを確認した。dependencyやkeyring failure時に暗号化をOFFへ落とすfallbackは使っていない。

## PolicyKit positive Gate

production action `io.github.nbe03xxx.llm-manager.apply-system-settings`はactive sessionで`auth_admin`、固定`/usr/bin/llm-manager-helper` annotationとしてauthorityに登録された。認証成功後は存在しないGate staging requestを`unsafe_request`でfail closedした。dismissはhelperを起動せずexit 126、一時deny ruleはpromptなしexit 127となり、ruleは直後に削除した。

実Gateで、desktop shellに残った`SUDO_UID=1000`とpkexecが付与した`PKEXEC_UID=1000`が同時に存在し、local helperが`invalid_invoking_user`へ誤停止することを発見した。localの正式境界は固定pkexecだけなので、local helperは`PKEXEC_UID`だけをtrusted identityとして使い、継承`SUDO_UID`を無視するよう修正した。remote helperの`SUDO_UID`境界は変更していない。

## Dedicated PolicyKit/systemd Gate

production allowlistをOllama以外へ広げず、disposable Gate専用action、root-owned固定helper、`llm-manager-phase4-gate.service`を一時配置した。認証後のhelper exit 0、unit `active`、`/run/llm-manager-phase4-gate/marker`存在を確認した。停止後にGate helper/action/unit/runtime directoryを削除し、daemon-reload後に全path不在を確認した。Ollama/OpenCode unitや設定は操作していない。

## Remaining

Debian 13でlocal/remote package、OpenSSH、PolicyKit、Secret Serviceの差異を確認する。Phase 5 GUIは未着手である。
