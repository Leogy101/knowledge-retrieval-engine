"""Compare preserved readiness before/after reports on a fixed coverage cohort."""
import argparse
import json
from pathlib import Path
import statistics


def compare(before, after):
    if before["freeze"]["files"] != after["freeze"]["files"]:
        raise ValueError("Comparisons require the identical frozen corpus and labels")
    first = {case["case_id"]: case for case in before["cases"]}
    last = {case["case_id"]: case for case in after["cases"]}
    if first.keys() != last.keys():
        raise ValueError("Comparisons require the identical case set")
    comparable = []
    changed = []
    for key, old in first.items():
        new = last[key]
        if any(old[field] != new[field] for field in ("query", "gold", "request", "required_expectation")):
            raise ValueError("Queries, labels, budgets and eligibility must remain unchanged")
        if old["equal_labeled_and_required_coverage_for_size_comparison"] and new["equal_labeled_and_required_coverage_for_size_comparison"]:
            comparable.append(key)
        a = old["algorithms"]["kre"]["metrics"]
        b = new["algorithms"]["kre"]["metrics"]
        changed.append({"case_id": key, "gold_spans": a["gold_spans"],
                        "covered_before": a["covered_gold_spans"], "covered_after": b["covered_gold_spans"],
                        "items_before": a["returned_items"], "items_after": b["returned_items"],
                        "bytes_before": a["context_bytes"], "bytes_after": b["context_bytes"]})
    def sizes(report, name):
        values = [report[key]["algorithms"][name]["metrics"]["context_bytes"] for key in comparable]
        return {"median_bytes": statistics.median(values) if values else None, "total_bytes": sum(values)}
    return {"independent_holdout": False, "status": "authorized_tuning_comparison",
            "fixture_hashes": before["freeze"]["files"], "cases": len(first),
            "before_summary": before["summary"], "after_summary": after["summary"],
            "fixed_complete_coverage_case_ids": comparable,
            "fixed_coverage_context": {"kre_before": sizes(first, "kre"), "kre_after": sizes(last, "kre"),
                                       "baseline_before": sizes(first, "overlap_baseline"), "baseline_after": sizes(last, "overlap_baseline")},
            "per_case_changes": changed,
            "limitations": ["Same previously inspected tuning cases; not independent generalization evidence.",
                            "Context comparison uses the intersection where both systems delivered all gold and required evidence in both runs.",
                            "Exact UTF-8 bytes include unchanged citation metadata; no provider tokenizer or generated answer is measured.",
                            "Warm timings from separate small runs are observations, not a statistically established speed improvement."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["fixed_coverage_context"], indent=2))


if __name__ == "__main__":
    main()
