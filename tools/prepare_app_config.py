"""Validate injected release settings without printing their values."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

def https_url(value, name, required=True):
    value = value.strip()
    if not value:
        if required:
            raise ValueError(name + " is required")
        return ""
    try:
        uri = urlsplit(value)
        valid = uri.scheme == "https" and uri.hostname and not uri.username and not uri.password and not uri.query and not uri.fragment
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(name + " must be HTTPS without credentials, query or fragment")
    return value.rstrip("/")

def prepare(env):
    base = https_url(env.get("CONTROLLER_BASE_URL", ""), "CONTROLLER_BASE_URL")
    https_url(env.get("CONTROLLER_DOWNLOAD_URL", ""), "CONTROLLER_DOWNLOAD_URL", required=False)
    if not env.get("CONTROLLER_APPLICATION_ID"):
        raise ValueError("CONTROLLER_APPLICATION_ID must preserve the installed package identity")
    return {"CONTROLLER_BASE_URL": base}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        config = prepare(os.environ)
    except ValueError as error:
        raise SystemExit(str(error))
    output = Path(args.output)
    output.write_text(json.dumps(config))
    output.chmod(0o600)
