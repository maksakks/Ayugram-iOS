#!/usr/bin/env python3
"""Builds the effective build configuration from the committed template.

The template in build-system/rufatgram-configuration.json contains
placeholders so that no real credentials live in git. Real values are supplied
through environment variables (GitHub Secrets in CI) and written to a
git-ignored file that Make.py receives via --configurationPath.

Recognised variables:
    RUFATGRAM_API_ID      Telegram API id
    RUFATGRAM_API_HASH    Telegram API hash
    RUFATGRAM_TEAM_ID     Apple team id
    RUFATGRAM_BUNDLE_ID   Bundle id of the application
    RUFATGRAM_URL_SCHEME  Custom URL scheme

Unset variables keep the template value. The script never prints secret
values, and refuses to write into a tracked file.
"""

import json
import os
import sys

TEMPLATE_KEYS = {
    "RUFATGRAM_API_ID": "api_id",
    "RUFATGRAM_API_HASH": "api_hash",
    "RUFATGRAM_TEAM_ID": "team_id",
    "RUFATGRAM_BUNDLE_ID": "bundle_id",
    "RUFATGRAM_URL_SCHEME": "app_specific_url_scheme",
}

PLACEHOLDER_VALUES = {
    "api_id": "0",
    "api_hash": "0" * 32,
    "team_id": "AAAAAAAAAA",
}


def fail(message):
    print("::error::" + message)
    raise SystemExit(1)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: prepare-configuration.py <template> <output>")

    template_path, output_path = sys.argv[1], sys.argv[2]
    if os.path.abspath(template_path) == os.path.abspath(output_path):
        fail("Refusing to overwrite the configuration template")

    with open(template_path) as file:
        configuration = json.load(file)

    for variable, key in TEMPLATE_KEYS.items():
        value = os.environ.get(variable)
        if value:
            configuration[key] = value

    missing = [key for key, placeholder in PLACEHOLDER_VALUES.items()
               if str(configuration.get(key, "")) == placeholder]
    if missing:
        # Keep the build running so the pipeline itself can be validated, but
        # make it obvious that this artifact cannot sign in to Telegram.
        print("::warning::Placeholder values are in use for: {}. "
              "Set the matching secrets before relying on this build."
              .format(", ".join(missing)))

    if configuration.get("bundle_id") == "ph.telegra.Telegraph":
        fail("Refusing to build with the official Telegram bundle id")

    with open(output_path, "w") as file:
        json.dump(configuration, file, indent="\t")

    print("Wrote configuration to {} (bundle id {}, team id {})".format(
        output_path, configuration.get("bundle_id"), configuration.get("team_id")))


if __name__ == "__main__":
    main()
