"""Blind judge calibration in the terminal (T48): the user grades the sampled answers of the two full S0 runs, one at a
time. Stop at any answer and run the same command to resume. A grade is final once confirmed. The agreement with the
judge is printed after the last grade, and never before.

No paid call. Run by the user.
Usage: uv run python scripts/grade.py <stack A run id> <stack B run id>
"""

import sys

from rag_playground import store
from rag_playground.rag import grading
from rag_playground.scoring.calibration import Agreement
from rag_playground.scoring.judging import ACCURACY_RUBRIC
from rag_playground.settings import CALIBRATION_TARGET, PASS_ACCURACY


def show(item: grading.Item, graded: int, size: int) -> None:
    print(f"\n{'=' * 70}\nAnswer {graded + 1} of {size}\n\n{ACCURACY_RUBRIC}\n"
          f"Scores 2 and 4 are in between. An answer passes at {PASS_ACCURACY} or above.\n\n"
          f"QUESTION:\n{item.question}\n\nREFERENCE ANSWER:\n{item.reference_answer}\n\n"
          f"SYSTEM ANSWER:\n{item.answer}\n")


def ask_grade() -> int | None:
    """A confirmed grade from 1 to 5, or None if the user stops."""
    while True:
        typed = input("Your accuracy grade (1-5, or q to stop): ").strip()
        if typed == "q":
            return None
        if typed in ("1", "2", "3", "4", "5") and input(f"Save {typed}? It is final (y/n): ").strip() == "y":
            return int(typed)


def report(result: Agreement) -> None:
    print(f"\nPass/fail agreement: {result.pass_fail:.0%} of {result.graded} answers "
          f"(95% Wilson interval {result.pass_fail_low:.0%} to {result.pass_fail_high:.0%})\n"
          f"Within 1 point: {result.within_one:.0%}\n"
          f"Target of {CALIBRATION_TARGET:.0%} pass/fail agreement: "
          f"{'reached' if result.target_reached else 'NOT reached, change the judge and repeat (plan.md 4.8)'}\n"
          "This describes the sample, equal per judge score, not all answers (T48).")


def main(run_a: int, run_b: int) -> None:
    conn = store.connect()
    calibration_id = grading.open_calibration(conn, run_a, run_b)
    while item := grading.next_item(conn, calibration_id):
        graded, size = grading.progress(conn, calibration_id)
        show(item, graded, size)
        grade = ask_grade()
        if grade is None:
            print(f"Stopped at {graded} of {size}. Run the same command to resume.")
            return
        grading.save_grade(conn, calibration_id, item.position, grade)
    report(grading.agreement(conn, calibration_id))


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
