import reflex as rx

import argparse
from pathlib import Path
from app.components.deepshield.datasets.loaders import (
    read_manifest,
    split_manifest,
    write_manifest,
)


def main():
    parser = argparse.ArgumentParser(
        description="Hash and group-split a real dataset manifest"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    write_manifest(
        split_manifest(read_manifest(args.manifest, args.root), args.seed),
        args.output,
    )


if __name__ == "__main__":
    main()
