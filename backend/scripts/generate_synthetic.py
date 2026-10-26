"""Generate the synthetic dataset one stage at a time (T29, T31): world, audit, docs, tests.

Usage: uv run python scripts/generate_synthetic.py world|audit
"""

import argparse
import sys

from rag_playground.datasets.audit_world import audit_world
from rag_playground.datasets.generate_world import generate_world
from rag_playground.datasets.schema import AUDIT_PATH, WORLD_PATH
from rag_playground.datasets.world import World, world_problems


def run_world() -> None:
    """Generate world.json, refusing to overwrite an existing one."""
    if WORLD_PATH.exists():
        raise SystemExit(f"{WORLD_PATH} already exists; delete it to regenerate.")
    world, cost = generate_world()
    WORLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORLD_PATH.write_text(world.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {WORLD_PATH} | cost ${cost:.4f}")
    print(f"employees {len(world.employees)} | services {len(world.services)} | "
          f"clients {len(world.clients)} | runbooks {len(world.runbooks)}")
    for problem in world_problems(world):
        print(f"PROBLEM: {problem}")


def run_audit() -> None:
    """Audit world.json and write the report next to it."""
    world = World.model_validate_json(WORLD_PATH.read_text(encoding="utf-8"))
    report, cost = audit_world(world)
    AUDIT_PATH.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {AUDIT_PATH} | cost ${cost:.4f} | issues {len(report.issues)}")
    for i, issue in enumerate(report.issues, 1):
        print(f"{i}. [{issue.kind}] {', '.join(issue.entity_ids)}: {issue.explanation}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["world", "audit"])
    args = parser.parse_args()
    {"world": run_world, "audit": run_audit}[args.stage]()


if __name__ == "__main__":
    main()
