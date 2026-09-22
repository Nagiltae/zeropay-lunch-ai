"""Create reproducible fixed-size KOMSCO restaurant manifests without NAVER calls."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.place_pipeline_cli import load_komsco_population, load_local_env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.size <= 0:
        parser.error("--size must be positive")
    root = Path(__file__).resolve().parents[2]
    load_local_env(root)
    population = load_komsco_population(root, None)
    ids = [reference.restaurant_id for reference in population.references]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for index in range(0, len(ids), args.size):
        batch_number = index // args.size + 1
        path = args.output_dir / f"komsco-batch-{batch_number:04d}.manifest"
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            "\n".join(str(value) for value in ids[index : index + args.size]) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        print(f"{path}: {min(index + args.size, len(ids)) - index} restaurants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
