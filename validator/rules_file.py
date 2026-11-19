"""Image availability and actual image SHA256 checks."""

import hashlib

from common import delivery_path


def check(ctx):
    errors = []
    for name, item in ctx["manifest"].items():
        path = delivery_path(ctx["root"], item["image"])
        if not path.is_file():
            errors.append({"type": "missing_image", "target": name})
        elif hashlib.sha256(path.read_bytes()).hexdigest() != item["image_sha256"]:
            errors.append({"type": "wrong_hash", "target": name})
    return errors
