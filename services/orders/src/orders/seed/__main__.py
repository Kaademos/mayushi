import argparse
import sys

from sqlalchemy.orm import Session

from orders.config import get_settings
from orders.db import get_engine
from orders.seed import build_dataset, load_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load deterministic seed data.")
    parser.add_argument("--seed", type=int, default=get_settings().seed)
    args = parser.parse_args(argv)

    data = build_dataset(args.seed)
    with Session(get_engine()) as session:
        counts = load_dataset(session, data)
    summary = ", ".join(f"{name}={count}" for name, count in counts.items())
    print(f"Seeded orders schema (seed={args.seed}): {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
