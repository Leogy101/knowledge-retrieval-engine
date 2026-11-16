"""Offline, content-minimizing quality checks for frozen paired-trial rubrics.

This module neither collects traces nor judges natural-language meaning. Exact
typed values are objective; semantic judgments require independently reviewed
attestations tied to the observed answer and (for citations) citation digest.
Supplied source snapshots/observations are trusted measurement inputs, not a
replacement for the producer's current authorization or freshness checks.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

MAX_BYTES = 2 * 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CATEGORIES = {"facts", "correctness", "constraints", "missing_evidence",
               "unnecessary_information", "recovery"}


class QualityError(ValueError):
    """Invalid bounded input; errors deliberately omit supplied values."""


def _fail() -> None:
    raise QualityError("invalid quality record")


def _bounded(value: Any) -> None:
    def visit(item: Any, depth: int) -> None:
        if depth > 32:
            _fail()
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            if len(item) > 4096:
                _fail()
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict and all(type(k) is str for k in item):
            if len(item) > 4096:
                _fail()
            for child in item.values():
                visit(child, depth + 1)
            return
        _fail()
    visit(value, 0)
    try:
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_BYTES:
            _fail()
    except (TypeError, ValueError, OverflowError, UnicodeError):
        _fail()


def strict_loads(text: str) -> Any:
    """Decode bounded JSON, rejecting duplicate keys and nonfinite constants."""
    if type(text) is not str:
        _fail()
    try:
        if len(text.encode("utf-8")) > MAX_BYTES:
            _fail()
        def pairs(entries: list[tuple[str, Any]]) -> dict[str, Any]:
            result = {}
            for key, value in entries:
                if key in result:
                    _fail()
                result[key] = value
            return result
        def constant(_: str) -> Any:
            _fail()
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
        _bounded(value)
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        _fail()


def _digest(value: Any) -> str:
    _bounded(value)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def answer_hash(answer: Any) -> str:
    return _digest(answer)


def citation_hash(citation: dict[str, Any]) -> str:
    return _digest(citation)


def _shape(value: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - optional:
        _fail()


def _identifier(value: Any) -> None:
    if type(value) is not str or not _ID.fullmatch(value):
        _fail()


def _hash(value: Any) -> None:
    if type(value) is not str or not _HASH.fullmatch(value):
        _fail()


def _boolean(value: Any) -> None:
    if type(value) is not bool:
        _fail()


def _count(value: Any) -> None:
    if type(value) is not int or value < 0 or value > 1_000_000:
        _fail()


def _items(value: Any, maximum: int = 256) -> list[Any]:
    if type(value) is not list or len(value) > maximum:
        _fail()
    return value


def _span(span: Any) -> None:
    _shape(span, {"source_id", "source_sha256", "line_start", "line_end"})
    _identifier(span["source_id"])
    _hash(span["source_sha256"])
    for key in ("line_start", "line_end"):
        _count(span[key])
    if not 1 <= span["line_start"] <= span["line_end"] or span["line_end"] - span["line_start"] > 10_000:
        _fail()


def _validate_rubric(rubric: Any) -> None:
    _bounded(rubric)
    _shape(rubric, {"format", "task_id", "task_sha256", "criteria"},
           {"sources", "citations", "required_evidence"})
    if rubric["format"] != "task-quality-rubric/1":
        _fail()
    _identifier(rubric["task_id"])
    _hash(rubric["task_sha256"])
    seen = set()
    for criterion in _items(rubric["criteria"], 64):
        _shape(criterion, {"id", "category", "critical", "method"}, {"path", "expected", "expectation"})
        _identifier(criterion["id"])
        if criterion["id"] in seen or type(criterion["category"]) is not str or criterion["category"] not in _CATEGORIES:
            _fail()
        seen.add(criterion["id"])
        _boolean(criterion["critical"])
        if criterion["method"] == "exact":
            if "path" not in criterion or "expected" not in criterion or "expectation" in criterion:
                _fail()
            for part in _items(criterion["path"], 16):
                if type(part) is str and len(part) <= 96:
                    continue
                if type(part) is int and 0 <= part < 4096:
                    continue
                _fail()
        elif criterion["method"] == "review":
            if ("path" in criterion or "expected" in criterion or
                    type(criterion.get("expectation")) is not str or
                    not criterion["expectation"].strip() or len(criterion["expectation"]) > 4096):
                _fail()
        else:
            _fail()
    sources = rubric.get("sources", {})
    if type(sources) is not dict or len(sources) > 256:
        _fail()
    for source_id, source in sources.items():
        _identifier(source_id)
        _shape(source, {"sha256", "eligible"})
        _hash(source["sha256"])
        _boolean(source["eligible"])
    for span in _items(rubric.get("required_evidence", [])):
        _span(span)
        source = sources.get(span["source_id"])
        if source is None or source["sha256"] != span["source_sha256"] or not source["eligible"]:
            _fail()
    if "citations" in rubric:
        policy = rubric["citations"]
        _shape(policy, {"require_any", "required_claims"})
        _boolean(policy["require_any"])
        claims = _items(policy["required_claims"], 64)
        for claim in claims:
            _identifier(claim)
        if len(set(claims)) != len(claims):
            _fail()
    policy = rubric.get("citations", {})
    if not rubric["criteria"] and not rubric.get("required_evidence") and not policy.get("require_any") and not policy.get("required_claims"):
        _fail()


def rubric_hash(rubric: dict[str, Any]) -> str:
    _validate_rubric(rubric)
    return _digest(rubric)


def _exact(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_exact(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(_exact(a, b) for a, b in zip(left, right))
    return left == right


def _at_path(answer: Any, path: list[Any]) -> tuple[bool, Any]:
    for part in path:
        if type(answer) is dict and type(part) is str and part in answer:
            answer = answer[part]
        elif type(answer) is list and type(part) is int and part < len(answer):
            answer = answer[part]
        else:
            return False, None
    return True, answer


def _all(values: list[bool | None]) -> bool | None:
    if False in values:
        return False
    return None if None in values else True


def _metric(values: list[bool | None] | None) -> dict[str, Any]:
    if values is None:
        return {"passed": None, "total": None, "unknown": None, "score": None}
    passed, unknown = values.count(True), values.count(None)
    return {"passed": passed, "total": len(values), "unknown": unknown,
            "score": passed / len(values) if values and not unknown else None}


def _review(review: Any, answer_digest: str | None, extra_required: set[str] = frozenset()) -> bool | None:
    _shape(review, {"verdict", "independent", "reviewer_ref", "answer_sha256"} | extra_required)
    if review["verdict"] is not None:
        _boolean(review["verdict"])
    _boolean(review["independent"])
    _identifier(review["reviewer_ref"])
    _hash(review["answer_sha256"])
    if answer_digest is None or review["answer_sha256"] != answer_digest:
        _fail()
    return review["verdict"] if review["independent"] else None


def score_trial(rubric: dict[str, Any], observation: dict[str, Any],
                sources: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a redacted deterministic score; unknown evidence stays unknown.

    Source text is supplied in memory, never fetched from a recorded path.
    Review attestations are trusted inputs, not cryptographic proof of review.
    Source eligibility is evaluated against the frozen supplied snapshot only.
    """
    digest = rubric_hash(rubric)
    _bounded(observation)
    _shape(observation, {"format", "task_id", "task_sha256", "rubric_sha256", "completion"},
           {"answer", "reviews", "citations", "citation_reviews", "evidence", "errors",
            "recovery", "unnecessary_information"})
    if (observation["format"] != "task-quality-observation/1" or
            observation["task_id"] != rubric["task_id"] or
            observation["task_sha256"] != rubric["task_sha256"] or
            observation["rubric_sha256"] != digest):
        _fail()
    if type(observation["completion"]) is not str or observation["completion"] not in {"completed", "incomplete", "cancelled", "error", "unknown"}:
        _fail()
    completion = None if observation["completion"] == "unknown" else observation["completion"] == "completed"
    answer_digest = answer_hash(observation["answer"]) if "answer" in observation else None
    criteria_by_id = {c["id"]: c for c in rubric["criteria"]}
    reviews = {}
    for review in _items(observation.get("reviews", []), 64):
        verdict = _review(review, answer_digest, {"criterion_id"})
        criterion_id = review["criterion_id"]
        _identifier(criterion_id)
        if criterion_id not in criteria_by_id or criteria_by_id[criterion_id]["method"] != "review" or criterion_id in reviews:
            _fail()
        reviews[criterion_id] = verdict
    groups: dict[str, list[bool | None]] = {category: [] for category in sorted(_CATEGORIES)}
    critical = [completion, True if answer_digest is not None else None]
    results = list(critical)
    for criterion in rubric["criteria"]:
        if criterion["method"] == "review":
            value = reviews.get(criterion["id"])
        elif answer_digest is None:
            value = None
        else:
            found, actual = _at_path(observation["answer"], criterion["path"])
            value = found and _exact(actual, criterion["expected"])
        groups[criterion["category"]].append(value)
        results.append(value)
        if criterion["critical"]:
            critical.append(value)
    source_map = rubric.get("sources", {})
    if sources is not None:
        _bounded(sources)
        if type(sources) is not dict or any(type(k) is not str or type(v) is not str for k, v in sources.items()):
            _fail()

    def valid_span(span: dict[str, Any]) -> bool | None:
        source = source_map.get(span["source_id"])
        if source is None or not source["eligible"] or span["source_sha256"] != source["sha256"]:
            return False
        if sources is None or span["source_id"] not in sources:
            return None
        text = sources[span["source_id"]]
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != source["sha256"]:
            return False
        return span["line_end"] <= len(text.splitlines())

    citations = observation.get("citations")
    exact_values = support_values = None
    citation_digest_values = []
    if citations is not None:
        exact_values, support_values = [], []
        for citation in _items(citations):
            _shape(citation, {"source_id", "source_sha256", "line_start", "line_end", "quote", "claim_id"})
            span = {key: citation[key] for key in ("source_id", "source_sha256", "line_start", "line_end")}
            _span(span)
            _identifier(citation["claim_id"])
            if type(citation["quote"]) is not str or not citation["quote"]:
                _fail()
            exact = valid_span(span)
            if exact is True:
                selected = "".join(sources[citation["source_id"]].splitlines(keepends=True)[citation["line_start"] - 1:citation["line_end"]])
                exact = citation["quote"] in selected
            exact_values.append(exact)
            support_values.append(None)
            citation_digest_values.append(citation_hash(citation))
    seen_reviews = set()
    for review in _items(observation.get("citation_reviews", [])):
        verdict = _review(review, answer_digest, {"citation_index", "citation_sha256"})
        index = review["citation_index"]
        _count(index)
        _hash(review["citation_sha256"])
        if citations is None or index >= len(citations) or index in seen_reviews or review["citation_sha256"] != citation_digest_values[index]:
            _fail()
        seen_reviews.add(index)
        support_values[index] = verdict
    if "citations" in rubric:
        policy = rubric["citations"]
        if citations is None:
            citation_pass = None
        else:
            citation_pass = _all(exact_values + support_values)
            if policy["require_any"] and not citations:
                citation_pass = False
            for claim in policy["required_claims"]:
                candidates = [_all([exact_values[i], support_values[i]]) for i, citation in enumerate(citations) if citation["claim_id"] == claim]
                supported = True if True in candidates else None if None in candidates else False
                citation_pass = _all([citation_pass, supported])
        critical.append(citation_pass)
        results.append(citation_pass)
    elif citations:
        # Emitted misinformation cannot escape the gate by omitting a policy.
        citation_pass = _all(exact_values + support_values)
        critical.append(citation_pass)
        results.append(citation_pass)
    evidence = observation.get("evidence")
    evidence_values = []
    verified_evidence = []
    if evidence is not None:
        for span in _items(evidence):
            _span(span)
            verified_evidence.append((span, valid_span(span)))
        if verified_evidence:
            # Incorrect/ineligible observed evidence is not excused by empty gold.
            evidence_validity = _all([valid for _, valid in verified_evidence])
            critical.append(evidence_validity)
            results.append(evidence_validity)
    for required in rubric.get("required_evidence", []):
        if evidence is None:
            evidence_values.append(None)
            continue
        covered, uncertain = set(), set()
        for observed, valid in verified_evidence:
            if observed["source_id"] == required["source_id"] and observed["source_sha256"] == required["source_sha256"]:
                points = range(max(required["line_start"], observed["line_start"]), min(required["line_end"], observed["line_end"]) + 1)
                if valid is True:
                    covered.update(points)
                elif valid is None:
                    uncertain.update(points)
        needed = set(range(required["line_start"], required["line_end"] + 1))
        evidence_values.append(True if needed <= covered else None if needed <= covered | uncertain else False)
    if evidence_values:
        critical.append(_all(evidence_values))
        results.append(_all(evidence_values))
    errors = observation.get("errors")
    unnecessary = observation.get("unnecessary_information")
    for value in (errors, unnecessary):
        if value is not None:
            _count(value)
    recovery = observation.get("recovery")
    if recovery is not None and (type(recovery) is not str or recovery not in {"not_needed", "recovered", "unrecovered", "unknown"}):
        _fail()
    if recovery == "unrecovered":
        critical.append(False)
        results.append(False)
    if unnecessary is not None and unnecessary > 0:
        results.append(False)
    return {
        "format": "quality-score/1", "scorer_version": "typed-review-1",
        "task_id": rubric["task_id"], "task_sha256": rubric["task_sha256"], "rubric_sha256": digest,
        "answer_sha256": answer_digest, "observation_sha256": _digest(observation),
        "completion_pass": completion, "critical_pass": _all(critical), "quality_pass": _all(results),
        "criteria": {category: _metric(values) for category, values in groups.items()},
        "citation_exactness": _metric(exact_values), "citation_support": _metric(support_values),
        "evidence_recall": _metric(evidence_values),
        "evidence_validity": _metric([valid for _, valid in verified_evidence] if evidence is not None else None),
        "unnecessary_information": unnecessary,
        "errors": errors, "recovery": recovery,
        "review_basis": "Exact typed values or supplied independent review attestations; no semantic model judge.",
    }
