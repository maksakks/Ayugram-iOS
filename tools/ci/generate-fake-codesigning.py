#!/usr/bin/env python3
"""Generates placeholder code signing assets for an unsigned prototype build.

The build system (build-system/Make/BuildConfiguration.py) selects
provisioning profiles by comparing each profile's application-identifier with
"<team_id>.<bundle_id>". The profiles shipped in build-system/fake-codesigning
belong to the official Telegram application, so they never match a custom
bundle id and Make.py aborts with "Could not find a valid aps-environment
entitlement". This script rebuilds the profile set for the configured team id
and bundle id, signed with the same placeholder identity that
build-system/Make/ImportCertificates.py already imports into the keychain.

These assets are for prototype builds only: they contain no real Apple
credentials and cannot be used to install on a device. Signed builds use the
real .p12 and .mobileprovision files supplied through GitHub Secrets.

Usage:
    python3 tools/ci/generate-fake-codesigning.py \
        --configuration build-system/rufatgram-configuration.json \
        --certificates build-system/fake-codesigning/certs \
        --output "$RUNNER_TEMP/rufatgram-fake-signing"
"""

import argparse
import datetime
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid

# Profile file name -> bundle id suffix (see profile_name_mapping in
# build-system/Make/BuildConfiguration.py).
SUFFIXES = {
    "Telegram": "",
    "SiriIntents": ".SiriIntents",
    "NotificationContent": ".NotificationContent",
    "NotificationService": ".NotificationService",
    "Share": ".Share",
    "WatchApp": ".watchkitapp",
    "WatchExtension": ".watchkitapp.watchkitextension",
    "Widget": ".Widget",
    "BroadcastUpload": ".BroadcastUpload",
    "SGActionRequestHandler": ".SGActionRequestHandler",
}

# Identifiers used by the upstream profiles in build-system/fake-codesigning.
TEMPLATE_TEAM_ID = "C67CF9S4VU"
TEMPLATE_BUNDLE_ID = "ph.telegra.Telegraph"

# Profile file name -> upstream template; targets without one use "Share".
TEMPLATE_PROFILES = {
    "Telegram": "Telegram",
    "SiriIntents": "Intents",
    "NotificationContent": "NotificationContent",
    "NotificationService": "NotificationService",
    "Share": "Share",
    "WatchApp": "WatchApp",
    "WatchExtension": "WatchExtension",
    "Widget": "Widget",
}


def run(arguments, check=True):
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        sys.stderr.write(result.stderr.decode("utf-8", "replace"))
        raise SystemExit("Command failed: {}".format(" ".join(arguments)))
    return result


def export_identity(p12_path, workdir):
    """Extracts the placeholder identity to PEM.

    OpenSSL 3 needs -legacy to read the RC2-encoded p12; LibreSSL on macOS
    reads it directly, so both spellings are attempted.
    """
    key_path = os.path.join(workdir, "key.pem")
    cert_path = os.path.join(workdir, "cert.pem")
    attempts = [
        ["openssl", "pkcs12", "-in", p12_path, "-nodes", "-passin", "pass:", "-legacy"],
        ["openssl", "pkcs12", "-in", p12_path, "-nodes", "-passin", "pass:"],
    ]
    for attempt in attempts:
        result = run(attempt, check=False)
        if result.returncode == 0:
            data = result.stdout.decode("utf-8", "replace")
            cert = data[data.find("-----BEGIN CERTIFICATE-----"):data.find("-----END CERTIFICATE-----") + len("-----END CERTIFICATE-----")]
            key = None
            for marker in ("PRIVATE KEY-----", "RSA PRIVATE KEY-----"):
                start = data.find("-----BEGIN " + marker)
                if start != -1:
                    key = data[start:data.find("-----END " + marker) + len("-----END " + marker)]
                    break
            if not cert or not key:
                raise SystemExit("The certificate archive does not contain a private key: {}".format(p12_path))
            with open(cert_path, "w") as file:
                file.write(cert + "\n")
            with open(key_path, "w") as file:
                file.write(key + "\n")
            return cert_path, key_path
    raise SystemExit("Could not read {}".format(p12_path))


def certificate_der(cert_path):
    return run(["openssl", "x509", "-in", cert_path, "-outform", "der"]).stdout


def read_profile_plist(path):
    """Returns the plist embedded in a CMS-signed .mobileprovision file."""
    with open(path, "rb") as file:
        data = file.read()
    start = data.find(b"<?xml")
    end = data.find(b"</plist>")
    if start == -1 or end == -1:
        raise SystemExit("Not a provisioning profile: {}".format(path))
    return plistlib.loads(data[start:end + len(b"</plist>")])


def rebrand(value, team_id, bundle_id):
    if isinstance(value, str):
        return value.replace(TEMPLATE_BUNDLE_ID, bundle_id).replace(TEMPLATE_TEAM_ID, team_id)
    if isinstance(value, list):
        return [rebrand(item, team_id, bundle_id) for item in value]
    if isinstance(value, dict):
        return {key: rebrand(item, team_id, bundle_id) for key, item in value.items()}
    return value


def template_entitlements(templates_dir, name, team_id, bundle_id):
    """Entitlements of the matching upstream fake profile, rebranded.

    The app requests entitlements such as carplay-messaging, iCloud and app
    groups; rules_apple rejects the build when the profile lacks any of them,
    so the upstream set is reused instead of maintaining a hand-written list.
    """
    template = TEMPLATE_PROFILES.get(name, "Share")
    entitlements = read_profile_plist(
        os.path.join(templates_dir, template + ".mobileprovision"))["Entitlements"]
    return rebrand(entitlements, team_id, bundle_id)


def build_profile(team_id, bundle_id, suffix, der, entitlements):
    identifier = "{}.{}{}".format(team_id, bundle_id, suffix)
    entitlements = dict(entitlements)
    entitlements["application-identifier"] = identifier
    entitlements["com.apple.developer.team-identifier"] = team_id
    return {
        "AppIDName": "RufatGram",
        "ApplicationIdentifierPrefix": [team_id],
        # plisttool compares ExpirationDate with a naive datetime, so these must
        # be plist <date> values, not strings.
        "CreationDate": datetime.datetime(2024, 1, 1),
        "DeveloperCertificates": [der],
        "Entitlements": entitlements,
        "ExpirationDate": datetime.datetime(2034, 1, 1),
        "Name": "RufatGram Prototype {}".format(suffix or "App"),
        "Platform": ["iOS"],
        "ProvisionedDevices": [],
        "TeamIdentifier": [team_id],
        "TeamName": "RufatGram",
        "TimeToLive": 3650,
        "UUID": str(uuid.uuid5(uuid.NAMESPACE_DNS, identifier)),
        "Version": 1,
    }


def write_signed_profile(profile, destination, workdir, cert_path, key_path):
    plist_path = tempfile.mktemp(suffix=".plist", dir=workdir)
    with open(plist_path, "wb") as file:
        plistlib.dump(profile, file)
    run([
        "openssl", "smime", "-sign", "-binary", "-nodetach",
        "-in", plist_path,
        "-signer", cert_path,
        "-inkey", key_path,
        "-outform", "der",
        "-out", destination,
    ])
    os.unlink(plist_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--certificates", required=True,
                        help="Directory with the placeholder .p12 and .cer files")
    parser.add_argument("--templates", default="build-system/fake-codesigning/profiles",
                        help="Directory with the upstream fake profiles used as entitlement templates")
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    with open(arguments.configuration) as file:
        configuration = json.load(file)
    team_id = configuration["team_id"]
    bundle_id = configuration["bundle_id"]

    if not team_id or not bundle_id:
        raise SystemExit("team_id and bundle_id are required in the configuration")

    certificate_files = [name for name in os.listdir(arguments.certificates)
                         if name.endswith(".p12")]
    if not certificate_files:
        raise SystemExit("No .p12 found in {}".format(arguments.certificates))

    output = os.path.abspath(arguments.output)
    certs_dir = os.path.join(output, "certs")
    profiles_dir = os.path.join(output, "profiles")
    shutil.rmtree(output, ignore_errors=True)
    os.makedirs(certs_dir)
    os.makedirs(profiles_dir)

    workdir = tempfile.mkdtemp(prefix="rufatgram-fake-signing-")
    try:
        p12_path = os.path.join(arguments.certificates, certificate_files[0])
        cert_path, key_path = export_identity(p12_path, workdir)
        der = certificate_der(cert_path)

        for name in os.listdir(arguments.certificates):
            shutil.copyfile(os.path.join(arguments.certificates, name),
                            os.path.join(certs_dir, name))

        for name, suffix in SUFFIXES.items():
            entitlements = template_entitlements(arguments.templates, name, team_id, bundle_id)
            profile = build_profile(team_id, bundle_id, suffix, der, entitlements)
            write_signed_profile(profile, os.path.join(profiles_dir, name + ".mobileprovision"),
                                 workdir, cert_path, key_path)

        for file_name in sorted(os.listdir(profiles_dir)):
            print("Wrote {}".format(os.path.join(profiles_dir, file_name)))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
