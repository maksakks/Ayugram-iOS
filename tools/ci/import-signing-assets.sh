#!/usr/bin/env bash
# Imports the signing certificate and provisioning profiles for a signed build.
#
# Inputs (environment):
#   BUILD_CERTIFICATE_BASE64  base64 of a .p12 containing the signing identity
#   P12_PASSWORD              password of the .p12
#   KEYCHAIN_PASSWORD         password for the temporary keychain
#   PROFILES_JSON_BASE64      base64 of a JSON object {"<Name>": "<base64 of .mobileprovision>"}
#   PROVISIONING_PROFILE_BASE64  base64 of a single .mobileprovision (used when PROFILES_JSON_BASE64 is unset)
#
# Writes profiles into build-system/rufatgram-codesigning/profiles so that
# Make.py can resolve them by application-identifier, and installs them into
# ~/Library/MobileDevice/Provisioning Profiles for xcodebuild.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILES_DIR="$REPO_ROOT/build-system/rufatgram-codesigning/profiles"
INSTALLED_DIR="$HOME/Library/MobileDevice/Provisioning Profiles"

fail() { echo "::error::$*" >&2; exit 1; }

install_profile() {
    local file="$1"
    local name uuid
    name="$(security cms -D -i "$file" 2>/dev/null | plutil -extract Name raw -o - - 2>/dev/null || true)"
    uuid="$(security cms -D -i "$file" 2>/dev/null | plutil -extract UUID raw -o - - 2>/dev/null || true)"
    if [ -z "$name" ] || [ -z "$uuid" ]; then
        fail "Profile $file is not a readable .mobileprovision file"
    fi
    mkdir -p "$INSTALLED_DIR"
    cp "$file" "$INSTALLED_DIR/$uuid.mobileprovision"
    echo "Installed profile: $name ($uuid)"
}

if [ -n "${KEYCHAIN_PASSWORD:-}" ] && [ -n "${BUILD_CERTIFICATE_BASE64:-}" ]; then
    KEYCHAIN_PATH="$RUNNER_TEMP/app-signing.keychain-db"
    CERT_PATH="$RUNNER_TEMP/build_certificate.p12"

    printf '%s' "$BUILD_CERTIFICATE_BASE64" | base64 --decode > "$CERT_PATH"
    security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
    security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"
    security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
    security import "$CERT_PATH" -P "${P12_PASSWORD:-}" -A -t cert -f pkcs12 -k "$KEYCHAIN_PATH"
    security set-key-partition-list -S apple-tool:,apple: -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH" > /dev/null
    security list-keychains -d user -s "$KEYCHAIN_PATH" login.keychain-db
    rm -f "$CERT_PATH"

    if ! security find-identity -v -p codesigning "$KEYCHAIN_PATH" | grep -q "1 valid identities found"; then
        echo "Available signing identities:"
        security find-identity -v -p codesigning "$KEYCHAIN_PATH"
        fail "The imported certificate has no valid codesigning identity. Check that the .p12 contains the private key and matches the provisioning profile."
    fi
    echo "Signing identity imported successfully."
else
    echo "::warning::No certificate secrets provided; relying on Xcode managed signing."
fi

mkdir -p "$PROFILES_DIR"
COUNT=0

if [ -n "${PROFILES_JSON_BASE64:-}" ]; then
    JSON_PATH="$RUNNER_TEMP/profiles.json"
    printf '%s' "$PROFILES_JSON_BASE64" | base64 --decode > "$JSON_PATH"
    python3 - "$JSON_PATH" "$PROFILES_DIR" <<'PY'
import base64, json, pathlib, sys

manifest = json.load(open(sys.argv[1]))
out = pathlib.Path(sys.argv[2])
for name, payload in manifest.items():
    safe = "".join(c for c in name if c.isalnum() or c in "-_")
    (out / f"{safe}.mobileprovision").write_bytes(base64.b64decode(payload))
print(f"Decoded {len(manifest)} provisioning profiles")
PY
    for profile in "$PROFILES_DIR"/*.mobileprovision; do
        install_profile "$profile"
        COUNT=$((COUNT + 1))
    done
elif [ -n "${PROVISIONING_PROFILE_BASE64:-}" ]; then
    printf '%s' "$PROVISIONING_PROFILE_BASE64" | base64 --decode > "$PROFILES_DIR/app.mobileprovision"
    install_profile "$PROFILES_DIR/app.mobileprovision"
    COUNT=1
fi

if [ "$COUNT" -eq 0 ]; then
    echo "::warning::No provisioning profiles provided."
fi
