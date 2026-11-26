"""Offline SHA-256 verification; standard library only. Run before recomputing outputs."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import re
import sys


def verify(root):
    root = Path(root).resolve()
    manifest = root / "CHECKSUMS.sha256"
    if not manifest.is_file():
        return {"successful": False, "checked_files": 0, "errors": ["Missing CHECKSUMS.sha256"]}
    errors, seen = [], set()
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            errors.append(f"Malformed checksum entry on line {number}")
            continue
        expected, name = match.groups()
        relative = PurePosixPath(name)
        if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                or ":" in name or name in seen):
            errors.append(f"Unsafe or duplicate path: {name}")
            continue
        seen.add(name)
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            errors.append(f"Path outside package: {name}")
            continue
        if not target.is_file():
            errors.append(f"Missing file: {name}")
            continue
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            errors.append(f"SHA-256 mismatch: {name}")
    if not seen:
        errors.append("No payload files listed")
    return {"successful": not errors, "checked_files": len(seen), "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    result = verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["successful"] else 1


if __name__ == "__main__":
    sys.exit(main())