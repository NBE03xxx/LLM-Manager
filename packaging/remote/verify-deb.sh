#!/bin/sh
set -eu

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    echo "usage: verify-deb.sh PACKAGE.deb" >&2
    exit 2
fi

package=$1
extract_root=$(mktemp -d /tmp/llm-manager-remote-deb-verify.XXXXXX)
trap 'rm -rf "$extract_root"' EXIT HUP INT TERM

dpkg-deb --extract "$package" "$extract_root"
helper="$extract_root/usr/bin/llm-manager-remote-helper"
metadata="$extract_root/usr/share/llm-manager-remote-helper/helper-metadata.json"
runtime="$extract_root/usr/lib/llm-manager-remote-helper/llm_manager"

[ -f "$helper" ]
[ -f "$metadata" ]
[ -f "$runtime/infrastructure/remote_helper_cli.py" ]
[ "$(stat -c %a "$helper")" = 755 ]
[ "$(stat -c %a "$metadata")" = 644 ]
[ "$(stat -c %a "$runtime/infrastructure/remote_helper_cli.py")" = 644 ]
[ "$(sed -n '1p' "$helper")" = '#!/usr/bin/python3 -I' ]
grep -Fq 'sys.path.insert(0, "/usr/lib/llm-manager-remote-helper")' "$helper"
grep -Fxq '{"package":"llm-manager-remote-helper","package_version":"0.1.0~dev0","protocol_version":1,"schema_version":"1.0"}' "$metadata"

[ ! -e "$extract_root/usr/bin/llm-manager-helper" ]
[ ! -e "$extract_root/usr/share/polkit-1" ]
[ ! -e "$extract_root/usr/lib/python3/dist-packages/llm_manager" ]
if find "$runtime" -name __pycache__ -o -name '*.pyc' | grep -q .; then
    echo "bytecode cache found in private runtime" >&2
    exit 1
fi

contents=$(dpkg-deb --contents "$package")
printf '%s\n' "$contents" | grep -Eq '^-rwxr-xr-x root/root +[0-9]+ .* ./usr/bin/llm-manager-remote-helper$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/llm-manager-remote-helper/helper-metadata.json$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/lib/llm-manager-remote-helper/llm_manager/infrastructure/remote_helper_cli.py$'

[ "$(dpkg-deb --field "$package" Package)" = llm-manager-remote-helper ]
depends=$(dpkg-deb --field "$package" Depends)
for dependency in python3 python3-cryptography sudo; do
    printf '%s\n' "$depends" | grep -Fq "$dependency"
done
for forbidden in python3-secretstorage openssh-client policykit-1 pkexec polkitd llm-manager\ \(; do
    if printf '%s\n' "$depends" | grep -Fq "$forbidden"; then
        echo "unexpected remote dependency: $forbidden" >&2
        exit 1
    fi
done
