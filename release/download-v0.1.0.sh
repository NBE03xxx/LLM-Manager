#!/bin/sh
set -eu

umask 022

release_version=v0.1.0
base_url="https://github.com/NBE03xxx/LLM-Manager/releases/download/$release_version"
primary_fingerprint=353F4D4F55175F537FBCD07C3E2532969B404FFD
signing_fingerprint=034DA1601E14BE534254BA4DD8F253C086BE34C2

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
target_dir="$script_dir/$release_version"

if [ -e "$target_dir" ]; then
    echo "refusing to overwrite existing download directory: $target_dir" >&2
    exit 1
fi

for required_command in curl gpg sha256sum awk; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        echo "required command not found: $required_command" >&2
        exit 1
    fi
done

mkdir -m 0755 "$target_dir"
verify_home=
completed=0

cleanup() {
    if [ -n "$verify_home" ] && [ -d "$verify_home" ]; then
        rm -rf -- "$verify_home"
    fi
    if [ "$completed" -ne 1 ] && [ -d "$target_dir" ]; then
        rm -rf -- "$target_dir"
    fi
}
trap cleanup EXIT HUP INT TERM

download_asset() {
    asset_name=$1
    output_path="$target_dir/$asset_name"
    echo "Downloading $asset_name"
    curl \
        --fail \
        --location \
        --proto '=https' \
        --retry 2 \
        --silent \
        --show-error \
        --output "$output_path.part" \
        "$base_url/$asset_name"
    mv -- "$output_path.part" "$output_path"
}

download_asset RELEASE_KEY.asc
download_asset SHA256SUMS
download_asset SHA256SUMS.asc
download_asset llm-manager-0.1.0.tar.gz
download_asset llm-manager-remote-helper.cdx.json
download_asset llm-manager-remote-helper_0.1.0_all.deb
download_asset llm-manager-remote-helper_0.1.0_ubuntu-26.04_environment-sbom.tar.xz
download_asset llm-manager.cdx.json
download_asset llm-manager_0.1.0_all.deb
download_asset llm-manager_0.1.0_debian-13_environment-sbom.tar.xz
download_asset llm-manager_0.1.0_ubuntu-26.04_environment-sbom.tar.xz

asset_count=$(find "$target_dir" -mindepth 1 -maxdepth 1 -type f -name '*' | wc -l)
if [ "$asset_count" -ne 11 ]; then
    echo "unexpected release asset count: $asset_count" >&2
    exit 1
fi

verify_home=$(mktemp -d /tmp/llm-manager-release-keyring.XXXXXX)
chmod 700 "$verify_home"
gpg --homedir "$verify_home" --batch --import "$target_dir/RELEASE_KEY.asc"

actual_fingerprints=$(
    gpg --homedir "$verify_home" --batch --with-colons --fingerprint --fingerprint \
        | awk -F: '$1 == "fpr" { print $10 }'
)
expected_fingerprints=$(printf '%s\n%s' "$primary_fingerprint" "$signing_fingerprint")
if [ "$actual_fingerprints" != "$expected_fingerprints" ]; then
    echo "release key fingerprint mismatch" >&2
    exit 1
fi

signature_status=$(
    gpg --homedir "$verify_home" --batch --status-fd 1 \
        --verify "$target_dir/SHA256SUMS.asc" "$target_dir/SHA256SUMS" 2>&1
)
printf '%s\n' "$signature_status"
printf '%s\n' "$signature_status" \
    | awk -v signing="$signing_fingerprint" -v primary="$primary_fingerprint" '
        $1 == "[GNUPG:]" && $2 == "VALIDSIG" && $3 == signing && $NF == primary {
            valid = 1
        }
        END { exit valid ? 0 : 1 }
    '

(
    cd "$target_dir"
    sha256sum --check SHA256SUMS
)

completed=1
echo
echo "Download and verification completed: $target_dir"
echo "Install the local GUI package with:"
echo "  cd '$target_dir'"
echo "  sudo apt install ./llm-manager_0.1.0_all.deb"
