"""Generate the synthetic dataset one stage at a time (T29, T31, T32): world, audit, docs, doc-audit.

Usage: uv run python scripts/generate_synthetic.py world|check|audit|docs|doc-audit [--sample]
"""

import argparse
import json
import sys

from rag_playground.datasets.audit_docs import audit_doc
from rag_playground.datasets.audit_world import audit_world
from rag_playground.datasets.doc_checks import number_problems
from rag_playground.datasets.documents import DocSpec, doc_specs
from rag_playground.datasets.generate_docs import write_doc
from rag_playground.datasets.generate_world import generate_world
from rag_playground.datasets.schema import AUDIT_PATH, CLAIM_ALLOWLIST_PATH, DOCS_AUDIT_PATH, KB_DIR, WORLD_PATH
from rag_playground.datasets.world import World, world_problems


def load_world() -> World:
    return World.model_validate_json(WORLD_PATH.read_text(encoding="utf-8"))


def allowed_claims() -> frozenset[str]:
    """Texts a human reviewed and accepted despite a claim word (with reasons in the file)."""
    if not CLAIM_ALLOWLIST_PATH.exists():
        return frozenset()
    return frozenset(json.loads(CLAIM_ALLOWLIST_PATH.read_text(encoding="utf-8")))


def run_check(sample: bool) -> None:
    """Run every code check on world.json."""
    problems = world_problems(load_world(), allowed_claims())
    for problem in problems:
        print(f"PROBLEM: {problem}")
    print(f"problems {len(problems)}")


def selected_specs(sample: bool) -> list[DocSpec]:
    """All document specs, or the first one of each top-level folder."""
    specs = doc_specs(load_world())
    if not sample:
        return specs
    first = {}
    for spec in specs:
        first.setdefault(spec.path.split("/")[0], spec)
    return list(first.values())


def run_world(sample: bool) -> None:
    """Generate world.json, refusing to overwrite an existing one."""
    if WORLD_PATH.exists():
        raise SystemExit(f"{WORLD_PATH} already exists; delete it to regenerate.")
    world, cost = generate_world()
    WORLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORLD_PATH.write_text(world.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {WORLD_PATH} | cost ${cost:.4f}")
    print(f"employees {len(world.employees)} | services {len(world.services)} | "
          f"clients {len(world.clients)} | runbooks {len(world.runbooks)}")
    for problem in world_problems(world, allowed_claims()):
        print(f"PROBLEM: {problem}")


def run_audit(sample: bool) -> None:
    """Audit world.json and write the report next to it."""
    report, cost = audit_world(load_world())
    AUDIT_PATH.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {AUDIT_PATH} | cost ${cost:.4f} | issues {len(report.issues)}")
    for i, issue in enumerate(report.issues, 1):
        print(f"{i}. [{issue.kind}] {', '.join(issue.entity_ids)}: {issue.explanation}")


def run_docs(sample: bool) -> None:
    """Write every missing KB document; existing documents are only re-checked."""
    total = 0.0
    for spec in selected_specs(sample):
        path = KB_DIR / spec.path
        if path.exists():
            problems = number_problems(path.read_text(encoding="utf-8"), spec.facts)
        else:
            markdown, problems, cost = write_doc(spec)
            total += cost
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(markdown, encoding="utf-8")
        words = len(path.read_text(encoding="utf-8").split())
        status = "ok" if not problems else "PROBLEMS " + "; ".join(problems)
        print(f"{spec.path} | {words} words | {status}")
    print(f"cost ${total:.4f}")


def run_doc_audit(sample: bool) -> None:
    """Audit every written document against its facts; write the report next to the world."""
    report = json.loads(DOCS_AUDIT_PATH.read_text(encoding="utf-8")) if DOCS_AUDIT_PATH.exists() else {}
    total = 0.0
    for spec in selected_specs(sample):
        audit, cost = audit_doc(spec, (KB_DIR / spec.path).read_text(encoding="utf-8"))
        total += cost
        report[spec.path] = audit.model_dump(mode="json")["issues"]
        print(f"{spec.path} | issues {len(audit.issues)}")
        for issue in audit.issues:
            print(f"   [{issue.kind}] {issue.fact} | {issue.explanation}")
    DOCS_AUDIT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {DOCS_AUDIT_PATH} | cost ${total:.4f}")


STAGES = {"world": run_world, "check": run_check, "audit": run_audit, "docs": run_docs, "doc-audit": run_doc_audit}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=list(STAGES))
    parser.add_argument("--sample", action="store_true", help="only the first document of each folder")
    args = parser.parse_args()
    STAGES[args.stage](args.sample)


if __name__ == "__main__":
    main()
