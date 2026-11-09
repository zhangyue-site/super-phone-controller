"""Stage a user-supplied ONNX for the controller's authenticated model endpoint."""

import argparse
import hashlib
import json
from pathlib import Path

MAX_MODEL_BYTES = 32 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path, help="New directory outside the checkout")
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.is_relative_to(root):
        parser.error("the model directory must be outside the checkout")
    if args.model.suffix.lower() != ".onnx":
        parser.error("the controller requires an ONNX export")
    if not 1 <= len(args.version) <= 128:
        parser.error("version must be 1–128 characters")

    with args.model.open("rb") as source:
        payload = source.read(MAX_MODEL_BYTES + 1)
    if not 0 < len(payload) <= MAX_MODEL_BYTES:
        parser.error("model must be between 1 byte and 32 MiB")

    digest = hashlib.sha256(payload).hexdigest()
    filename = f"{digest}.onnx"
    output.mkdir(mode=0o700)
    (output / filename).write_bytes(payload)
    manifest = {
        "format": "onnx",
        "version": args.version,
        "file": filename,
        "sha256": digest,
        "size": len(payload),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
