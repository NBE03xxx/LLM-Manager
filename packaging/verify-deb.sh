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
launcher="$extract_root/usr/bin/llm-manager"
review="$extract_root/usr/bin/llm-manager-restore-review"
execute="$extract_root/usr/bin/llm-manager-restore-execute"
setup="$extract_root/usr/bin/llm-manager-restore-setup"
policy="$extract_root/usr/share/polkit-1/actions/io.github.nbe03xxx.llm-manager.policy"
metadata="$extract_root/usr/share/llm-manager/helper-metadata.json"
desktop="$extract_root/usr/share/applications/io.github.nbe03xxx.llm-manager.desktop"
icon="$extract_root/usr/share/icons/hicolor/scalable/apps/io.github.nbe03xxx.llm-manager.svg"
copyright="$extract_root/usr/share/doc/llm-manager/copyright"
notices="$extract_root/usr/share/doc/llm-manager/THIRD_PARTY_NOTICES.md"
sbom="$extract_root/usr/share/doc/llm-manager/llm-manager.cdx.json"

[ -f "$launcher" ]
[ -f "$helper" ]
[ -f "$review" ]
[ -f "$execute" ]
[ -f "$setup" ]
[ "$(stat -c %a "$setup")" = 755 ]
[ "$(sed -n '1p' "$setup")" = '#!/usr/bin/python3 -I' ]
grep -Fq 'from llm_manager.infrastructure.root_restore_setup_cli import main' "$setup"
grep -Fq 'sys.dont_write_bytecode = True' "$setup"
[ "$(stat -c %a "$execute")" = 755 ]
[ "$(sed -n '1p' "$execute")" = '#!/usr/bin/python3 -I' ]
grep -Fq 'from llm_manager.infrastructure.root_restore_execute_cli import main' "$execute"
grep -Fq 'sys.dont_write_bytecode = True' "$execute"
[ "$(stat -c %a "$review")" = 755 ]
[ "$(sed -n '1p' "$review")" = '#!/usr/bin/python3 -I' ]
grep -Fq 'from llm_manager.infrastructure.root_restore_review_cli import main' "$review"
grep -Fq 'sys.dont_write_bytecode = True' "$review"
grep -Fq '<annotate key="org.freedesktop.policykit.exec.path">/usr/bin/llm-manager-restore-review</annotate>' "$policy"
grep -Fq '<annotate key="org.freedesktop.policykit.exec.path">/usr/bin/llm-manager-restore-execute</annotate>' "$policy"
[ -f "$policy" ]
[ -f "$metadata" ]
[ -f "$desktop" ]
[ -f "$icon" ]
[ -f "$copyright" ]
[ -f "$notices" ]
[ -f "$sbom" ]
[ "$(stat -c %a "$launcher")" = 755 ]
[ "$(stat -c %a "$helper")" = 755 ]
[ "$(stat -c %a "$policy")" = 644 ]
[ "$(stat -c %a "$metadata")" = 644 ]
[ "$(stat -c %a "$copyright")" = 644 ]
[ "$(stat -c %a "$notices")" = 644 ]
[ "$(stat -c %a "$sbom")" = 644 ]
[ "$(sed -n '1p' "$helper")" = '#!/usr/bin/python3 -I' ]
[ "$(sed -n '1p' "$launcher")" = '#!/usr/bin/python3 -I' ]
grep -Fq 'from llm_manager.ui.qt_app import main' "$launcher"
grep -Fq 'sys.dont_write_bytecode = True' "$helper"
grep -Fq '<annotate key="org.freedesktop.policykit.exec.path">/usr/bin/llm-manager-helper</annotate>' "$policy"
grep -Fxq '{"package":"llm-manager","package_version":"0.1.0","protocol_version":1,"schema_version":"1.0"}' "$metadata"
grep -Fxq 'Exec=/usr/bin/llm-manager' "$desktop"
grep -Fxq 'TryExec=/usr/bin/llm-manager' "$desktop"
grep -Fxq 'Icon=io.github.nbe03xxx.llm-manager' "$desktop"
grep -Fxq 'Terminal=false' "$desktop"
grep -Fq 'Copyright: 2026 NBE03xxx' "$copyright"
python3 -m json.tool "$sbom" >/dev/null
grep -Fq 'pkg:deb/llm-manager@0.1.0' "$sbom"

contents=$(dpkg-deb --contents "$package")
printf '%s\n' "$contents" | grep -Eq '^-rwxr-xr-x root/root +[0-9]+ .* ./usr/bin/llm-manager-restore-setup$'
printf '%s\n' "$contents" | grep -Eq '^-rwxr-xr-x root/root +[0-9]+ .* ./usr/bin/llm-manager-restore-review$'
printf '%s\n' "$contents" | grep -Eq '^-rwxr-xr-x root/root +[0-9]+ .* ./usr/bin/llm-manager-restore-execute$'
printf '%s\n' "$contents" | grep -Eq '^-rwxr-xr-x root/root +[0-9]+ .* ./usr/bin/llm-manager$'
printf '%s\n' "$contents" | grep -Eq '^-rwxr-xr-x root/root +[0-9]+ .* ./usr/bin/llm-manager-helper$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/polkit-1/actions/io.github.nbe03xxx.llm-manager.policy$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/llm-manager/helper-metadata.json$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/applications/io.github.nbe03xxx.llm-manager.desktop$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/icons/hicolor/scalable/apps/io.github.nbe03xxx.llm-manager.svg$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/doc/llm-manager/copyright$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/doc/llm-manager/THIRD_PARTY_NOTICES.md$'
printf '%s\n' "$contents" | grep -Eq '^-rw-r--r-- root/root +[0-9]+ .* ./usr/share/doc/llm-manager/llm-manager.cdx.json$'

depends=$(dpkg-deb --field "$package" Depends)
for dependency in python3 openssh-client pkexec polkitd python3-cryptography python3-pyside6.qtcore python3-pyside6.qtwidgets python3-secretstorage systemd; do
    printf '%s\n' "$depends" | grep -Fq "$dependency"
done
