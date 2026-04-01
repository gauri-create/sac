#!/usr/bin/env python3
"""
scripts/add_person.py
Register a new person by pointing to their image files.

Usage:
    python scripts/add_person.py "Alice Smith" /path/to/alice1.jpg /path/to/alice2.jpg

The images are copied into data/known_faces/Alice_Smith/ and encodings are rebuilt.
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from face_engine.encoding import EncodingManager


def main():
    parser = argparse.ArgumentParser(description="Add a person to the face recognition dataset.")
    parser.add_argument("name", help="Full display name (e.g. 'Alice Smith')")
    parser.add_argument("images", nargs="+", help="Paths to image files containing this person's face")
    args = parser.parse_args()

    name = args.name
    images = [Path(p) for p in args.images]

    # Validate all files exist
    for img in images:
        if not img.exists():
            print(f"[ERROR] File not found: {img}")
            sys.exit(1)

    # Copy images to known_faces/<Name>/
    safe_name = name.replace(" ", "_")
    dest_dir  = Path("data/known_faces") / safe_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for img in images:
        dest = dest_dir / img.name
        shutil.copy2(img, dest)
        copied.append(str(dest))
        print(f"  Copied → {dest}")

    # Rebuild encodings
    print(f"\nBuilding encodings for '{name}'…")
    mgr   = EncodingManager()
    count = mgr.build_encodings(force_rebuild=True)
    print(f"Done. {count} identit{'y' if count == 1 else 'ies'} in database.")


if __name__ == "__main__":
    main()
