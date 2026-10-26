"""Generate the synthetic dataset one stage at a time (T29, T31, T32): world, audit, docs, doc-audit.

Usage: uv run python scripts/generate_synthetic.py world|check|audit|docs|doc-audit|candidates|topup|verify|assemble [--sample] [--category C]
"""

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import APIStatusError

from rag_playground.datasets.audit_docs import audit_doc
from rag_playground.datasets.assemble import QUOTAS, assemble, distinct_facts, doc_kind, kind_cap, paths_kind
from rag_playground.datasets.audit_world import audit_world
from rag_playground.datasets.candidates import (
    TWO_DOC, Candidate, candidate_problems, comparative_pairs, multi_doc_pairs,
)
from rag_playground.datasets.doc_checks import number_problems
from rag_playground.datasets.documents import DocSpec, doc_specs
from rag_playground.datasets.generate_docs import write_doc
from rag_playground.datasets.generate_tests import (
    pair_candidates, single_doc_candidates, topup_candidates, unanswerable_candidates,
)
from rag_playground.datasets.generate_world import generate_world
from rag_playground.datasets.schema import (
    Category,
    AUDIT_PATH, CANDIDATES_PATH, CLAIM_ALLOWLIST_PATH, DOCS_AUDIT_PATH, KB_DIR, TESTS_PATH, VERIFICATION_PATH,
    WORLD_PATH,
)
from rag_playground.datasets.verify_tests import accepted, verify_batch
from rag_playground.datasets.world import World, world_problems


def load_world() -> World:
    return World.model_validate_json(WORLD_PATH.read_text(encoding="utf-8"))


def allowed_claims() -> frozenset[str]:
    """Texts a human reviewed and accepted despite a claim word (with reasons in the file)."""
    if not CLAIM_ALLOWLIST_PATH.exists():
        return frozenset()
    return frozenset(json.loads(CLAIM_ALLOWLIST_PATH.read_text(encoding="utf-8")))


def run_check(args: argparse.Namespace) -> None:
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


def run_world(args: argparse.Namespace) -> None:
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


def run_audit(args: argparse.Namespace) -> None:
    """Audit world.json and write the report next to it."""
    report, cost = audit_world(load_world())
    AUDIT_PATH.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {AUDIT_PATH} | cost ${cost:.4f} | issues {len(report.issues)}")
    for i, issue in enumerate(report.issues, 1):
        print(f"{i}. [{issue.kind}] {', '.join(issue.entity_ids)}: {issue.explanation}")


def run_docs(args: argparse.Namespace) -> None:
    """Write every missing KB document; existing documents are only re-checked."""
    total = 0.0
    for spec in selected_specs(args.sample):
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


def run_doc_audit(args: argparse.Namespace) -> None:
    """Audit every written document against its facts; write the report next to the world."""
    report = json.loads(DOCS_AUDIT_PATH.read_text(encoding="utf-8")) if DOCS_AUDIT_PATH.exists() else {}
    total = 0.0
    for spec in selected_specs(args.sample):
        audit, cost = audit_doc(spec, (KB_DIR / spec.path).read_text(encoding="utf-8"))
        total += cost
        report[spec.path] = audit.model_dump(mode="json")["issues"]
        print(f"{spec.path} | issues {len(audit.issues)}")
        for issue in audit.issues:
            print(f"   [{issue.kind}] {issue.fact} | {issue.explanation}")
    DOCS_AUDIT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {DOCS_AUDIT_PATH} | cost ${total:.4f}")


def kb_texts() -> dict[str, str]:
    """Every KB document as {path: markdown}."""
    return {s.path: (KB_DIR / s.path).read_text(encoding="utf-8") for s in doc_specs(load_world())}


def chunks(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def candidate_jobs(sample: bool) -> list:
    """Generation calls for all candidates; the sample takes one call of each kind."""
    world, kb = load_world(), kb_texts()
    take = (lambda batches: batches[:1]) if sample else (lambda batches: batches)
    jobs = [lambda b=b: single_doc_candidates(b, kb) for b in take(chunks(list(kb), 4))]
    jobs += [lambda b=b: pair_candidates(b, "multi_doc", kb) for b in take(chunks(multi_doc_pairs(world), 5))]
    jobs += [lambda b=b: pair_candidates(b, "comparative", kb) for b in take(chunks(comparative_pairs(world), 5))]
    return jobs + [lambda: unanswerable_candidates(6 if sample else 40, kb)]


def run_candidates(args: argparse.Namespace) -> None:
    """Generate candidates (5 calls in parallel), write them, and report code-check results."""
    path = CANDIDATES_PATH.with_name("candidates_sample.jsonl") if args.sample else CANDIDATES_PATH
    if path.exists():
        raise SystemExit(f"{path} already exists; delete it to regenerate.")
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda job: job(), candidate_jobs(args.sample)))
    candidates = [c for batch, _ in results for c in batch]
    path.write_text("".join(c.model_dump_json() + "\n" for c in candidates), encoding="utf-8")
    kb = kb_texts()
    failing = [(c, p) for c in candidates if (p := candidate_problems(c, kb))]
    for c, problems in failing:
        print(f"FAIL [{c.category}] {c.question} | {'; '.join(problems)}")
    print(f"wrote {path} | {len(candidates)} candidates | code-check failures {len(failing)} | "
          f"cost ${sum(cost for _, cost in results):.4f}")
    print("per category:", dict(Counter(c.category.value for c in candidates)))


def load_candidates() -> list[Candidate]:
    lines = CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()
    return [Candidate.model_validate_json(line) for line in lines if line.strip()]


def load_verification() -> list[dict]:
    if not VERIFICATION_PATH.exists():
        return []
    return [json.loads(line) for line in VERIFICATION_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def verification_rows(batch: list[Candidate], verdicts: list) -> list[dict]:
    return [{"candidate": c.model_dump(mode="json"), "verdict": v.model_dump(), "accepted": accepted(c, v)}
            for c, v in zip(batch, verdicts)]


def run_verify(args: argparse.Namespace) -> None:
    """Code-check new candidates, verify the passing ones against the whole KB (10 per call, --workers in parallel).
    Each batch is appended as soon as it returns, so a failed call loses no paid work; rerunning resumes."""
    kb = kb_texts()
    done = {r["candidate"]["question"] for r in load_verification()}
    passing = [c for c in load_candidates() if c.question not in done and not candidate_problems(c, kb)]
    kb_text = "\n\n".join(f"=== {path} ===\n{text}" for path, text in kb.items())
    cost, failed = 0.0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool, VERIFICATION_PATH.open("a", encoding="utf-8") as f:
        futures = {pool.submit(verify_batch, b, kb_text): b for b in chunks(passing, 10)}
        for future in as_completed(futures):
            try:
                verdicts, batch_cost = future.result()
            except APIStatusError as e:
                failed += 1
                print(f"batch failed: {e.status_code} {e.message}")
                continue
            cost += batch_cost
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in verification_rows(futures[future], verdicts))
            f.flush()
    rows = load_verification()
    kept = Counter(r["candidate"]["category"] for r in rows if r["accepted"])
    seen = Counter(r["candidate"]["category"] for r in rows)
    print(f"verified {len(rows)} in total | failed batches {failed} | cost ${cost:.4f}")
    for category in seen:
        print(f"  {category}: accepted {kept[category]} of {seen[category]}")


def short_kinds(category: Category, kb: dict[str, str]) -> set[str]:
    """Document kinds with fewer than twice their selection cap in distinct facts among passing candidates."""
    passing = [c for c in load_candidates() if c.category == category and not candidate_problems(c, kb)]
    passing = Counter(doc_kind(c) for c in distinct_facts(passing))
    need = 2 * kind_cap(category, QUOTAS[category])
    kinds = {paths_kind(p) for p in category_pairs(category)} if category in TWO_DOC else {paths_kind([d]) for d in kb}
    return {k for k in kinds if passing[k] < need}


def category_pairs(category: Category) -> list[tuple[str, str]]:
    world = load_world()
    return multi_doc_pairs(world) if category == Category.MULTI_DOC else comparative_pairs(world)


def topup_jobs(category: Category, kb: dict[str, str], kinds: list[str] | None) -> list:
    """Generation calls for the documents or pairs of the given kinds, or of the short kinds."""
    short = set(kinds) if kinds else short_kinds(category, kb)
    print(f"top-up kinds for {category}: {sorted(short)}")
    existing = [c.question for c in load_candidates() if c.category == category]
    if category in TWO_DOC:
        pairs = [p for p in category_pairs(category) if paths_kind(p) in short]
        return [lambda b=b: pair_candidates(b, category, kb, existing) for b in chunks(pairs, 5)]
    docs = [d for d in kb if paths_kind([d]) in short]
    return [lambda b=b: topup_candidates(b, category, existing, kb) for b in chunks(docs, 4)]


def run_topup(args: argparse.Namespace) -> None:
    """Append candidates of one category (--category) for the given (--kinds) or short document kinds.
    Each call's candidates are appended as soon as it returns, so a failed call loses no paid work."""
    category, kb = Category(args.category), kb_texts()
    cost, new, failed = 0.0, [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool, CANDIDATES_PATH.open("a", encoding="utf-8") as f:
        for future in as_completed([pool.submit(job) for job in topup_jobs(category, kb, args.kinds)]):
            try:
                batch, batch_cost = future.result()
            except APIStatusError as e:
                failed += 1
                print(f"call failed: {e.status_code} {e.message}")
                continue
            cost += batch_cost
            kept = [c for c in batch if c.category == category]
            new += kept
            f.writelines(c.model_dump_json() + "\n" for c in kept)
            f.flush()
    passing = sum(not candidate_problems(c, kb) for c in new)
    print(f"appended {len(new)} {category} candidates, {passing} pass the code checks | failed calls {failed} | "
          f"cost ${cost:.4f}")


def run_assemble(args: argparse.Namespace) -> None:
    """Select verified candidates per quota and write tests.jsonl."""
    rows = [json.loads(line) for line in VERIFICATION_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    tests = assemble([Candidate.model_validate(r["candidate"]) for r in rows if r["accepted"]])
    TESTS_PATH.write_text("".join(t.model_dump_json() + "\n" for t in tests), encoding="utf-8")
    print(f"wrote {TESTS_PATH} | {len(tests)} tests")
    print("per category and split:", dict(Counter((t.category.value, t.split.value) for t in tests)))


STAGES = {"world": run_world, "check": run_check, "audit": run_audit, "docs": run_docs, "doc-audit": run_doc_audit,
          "candidates": run_candidates, "topup": run_topup, "verify": run_verify, "assemble": run_assemble}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=list(STAGES))
    parser.add_argument("--sample", action="store_true", help="only the first document of each folder")
    parser.add_argument("--category", help="category for the topup stage")
    parser.add_argument("--workers", type=int, default=5, help="parallel calls for the verify and topup stages")
    parser.add_argument("--kinds", nargs="+", help="document kinds for the topup stage, such as company+employees")
    args = parser.parse_args()
    STAGES[args.stage](args)


if __name__ == "__main__":
    main()
