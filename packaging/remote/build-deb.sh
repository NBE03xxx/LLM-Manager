#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: build-deb.sh OUTPUT.deb" >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
    SOURCE_DATE_EPOCH=$(dpkg-parsechangelog -l "$repo_root/debian/changelog" -S Timestamp)
    export SOURCE_DATE_EPOCH
fi
output=$1
case "$output" in
    /*) ;;
    *) output=$(pwd)/$output ;;
esac

package_root=$(mktemp -d /tmp/llm-manager-remote-deb.XXXXXX)
trap 'rm -rf "$package_root"' EXIT HUP INT TERM

install -d -m 0755 \
    "$package_root/DEBIAN" \
    "$package_root/usr/bin" \
    "$package_root/usr/lib/llm-manager-remote-helper" \
    "$package_root/usr/share/doc/llm-manager-remote-helper" \
    "$package_root/usr/share/llm-manager-remote-helper"
install -m 0644 "$script_dir/control" "$package_root/DEBIAN/control"
install -m 0755 "$script_dir/bin/llm-manager-remote-helper" \
    "$package_root/usr/bin/llm-manager-remote-helper"
install -m 0644 "$script_dir/helper-metadata.json" \
    "$package_root/usr/share/llm-manager-remote-helper/helper-metadata.json"
install -m 0644 "$repo_root/debian/copyright" \
    "$package_root/usr/share/doc/llm-manager-remote-helper/copyright"
install -m 0644 "$repo_root/THIRD_PARTY_NOTICES.md" \
    "$package_root/usr/share/doc/llm-manager-remote-helper/THIRD_PARTY_NOTICES.md"
install -m 0644 "$repo_root/packaging/sbom/llm-manager-remote-helper.cdx.json" \
    "$package_root/usr/share/doc/llm-manager-remote-helper/sbom.cdx.json"
cp -a "$repo_root/src/llm_manager" \
    "$package_root/usr/lib/llm-manager-remote-helper/llm_manager"
find "$package_root/usr/lib/llm-manager-remote-helper" -type d -name __pycache__ \
    -prune -exec rm -rf '{}' +
find "$package_root/usr/lib/llm-manager-remote-helper" -type d -exec chmod 0755 '{}' +
find "$package_root/usr/lib/llm-manager-remote-helper" -type f -exec chmod 0644 '{}' +

mkdir -p "$(dirname -- "$output")"
dpkg-deb --root-owner-group --build "$package_root" "$output"
