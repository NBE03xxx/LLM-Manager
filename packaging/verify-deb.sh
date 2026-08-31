#!/bin/sh
set -eu

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    echo "usage: verify-deb.sh PACKAGE.deb" >&2
    exit 2
fi

package=$1
extract_root=$(mktemp -d /tmp/llm-manager-deb-verify.XXXXXX)
trap 'rm -rf "$extract_root"' EXIT HUP INT TERM

dpkg-deb --extract "$package" "$extract_root"
helper="$extract_root/usr/bin/llm-manager-helper"
policy="$extract_root/usr/share/polkit-1/actions/io.github.nbe03xxx.llm-manager.policy"
metadata="$extract_root/usr/share/llm-manager/helper-metadata.json"

[ -f "$helper" ]
[ -f "$policy" ]
[ -f "$metadata" ]
[ "$(stat -c %a "$helper")" = 755 ]
[ "$(stat -c %a "$policy")" = 644 ]
[ "$(stat -c %a "$metadata")" = 644 ]
[ "$(sed -n '1p' "$helper")" = '#!/usr/bin/python3 -I' ]
grep -Fq 'sys.dont_write_bytecode = True' "$helper"
grep -Fq '<annotate key="org.freedesktop.policykit.exec.path">/usr/bin/llm-manager-helper</annotate>' "$policy"
grep -Fxq '{"package":"llm-manager","package_version":"0.1.0~dev0","protocol_version":1,"schema_version":"1.0"}' "$metadata"

contents=$(dpkg-deb --contents "$package")
printf '%s\n' "$contents" | grep -Eq '^-rwxr-xr-x root/root +[0-9]+ .* ./usr/bin/llm-manager-helper$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/polkit-1/actions/io.github.nbe03xxx.llm-manager.policy$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/llm-manager/helper-metadata.json$'

depends=$(dpkg-deb --field "$package" Depends)
for dependency in python3 openssh-client pkexec polkitd python3-cryptography python3-secretstorage systemd; do
    printf '%s\n' "$depends" | grep -Fq "$dependency"
done
