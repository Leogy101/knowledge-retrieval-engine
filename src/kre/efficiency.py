"""Offline, metadata-only paired measurement. No network, tracing service or model calls.

This imports deliberately scoped receipts. It cannot discover omitted requests or
prove a collector's completeness assertion. Text is measured by hash/UTF-8 size;
raw prompts, tool bodies, request identifiers and exception text are not exported.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import sys

MAX_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 10000
HASH = re.compile(r"[0-9a-f]{64}\Z")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z")
STATES = {"started", "completed", "failed", "cancelled", "incomplete"}
COVERAGE = {"complete", "partial", "unknown"}
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
              "reasoning_tokens", "total_tokens")
CONTEXT_KEYS = ("model_input_bytes", "injected_tool_bytes", "injected_evidence_bytes", "estimated_input_tokens")
TIME_KEYS = ("completion_seconds", "retrieval_core_seconds", "retrieval_round_trip_seconds",
             "validation_seconds", "routing_seconds", "local_cpu_seconds", "setup_seconds",
             "setup_cpu_seconds", "storage_bytes")


class MeasurementError(ValueError):
    """Only fixed error codes are returned; never include offending trace content."""


def _fail(code="invalid_measurement"):
    raise MeasurementError(code)


def _object(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or not set(required) <= set(value):
        _fail("invalid_fields")
    return value


def _number(value, *, integer=False, nullable=True):
    if value is None and nullable:
        return None
    if type(value) not in ((int,) if integer else (int, float)) or value < 0 or value > 10**18 or not math.isfinite(value):
        _fail("invalid_number")
    return value


def _hash(value, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not HASH.fullmatch(value):
        _fail("invalid_fingerprint")
    return value


def _label(value):
    if not isinstance(value, str) or not LABEL.fullmatch(value):
        _fail("invalid_label")
    return value


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        _fail("invalid_json")


def fingerprint(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def model_configuration_sha256(configuration):
    """Requested provider/model/revision/reasoning identity, independent of prompt text."""
    return fingerprint({key: configuration[key] for key in ("provider", "model", "model_revision", "reasoning_sha256")})


def measure_content(text):
    """Measure each actual transmission separately; returned receipt stores no text."""
    if not isinstance(text, str):
        _fail("invalid_content")
    try:
        raw = text.encode("utf-8")
    except UnicodeError:
        _fail("invalid_content")
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def strict_loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail("duplicate_json_key")
            result[key] = value
        return result
    try:
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
            _fail("json_byte_limit")
        value = json.loads(text, object_pairs_hook=pairs,
                           parse_constant=lambda _: _fail("nonfinite_json"))
        _canonical(value)
        return value
    except MeasurementError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _fail("invalid_json")


def load_json(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            _fail("json_byte_limit")
        return strict_loads(raw.decode("utf-8"))
    except MeasurementError:
        raise
    except (OSError, ValueError, UnicodeError):
        _fail("invalid_file")


def normalize_usage(usage):
    """Normalize explicit cache semantics, retaining reported total independently.

    Input may include cache or exclude both cache buckets. Output must explicitly
    include reasoning: unsupported token semantics remain rejected, not guessed.
    A reported total can remain known when its breakdown is unavailable.
    """
    empty = {key: None for key in TOKEN_KEYS}
    empty.update(uncached_input_tokens=None, provider_reported_total=None,
                 source_kind=None, provenance_sha256=None)
    if usage is None:
        return empty
    allowed = set(TOKEN_KEYS) | {"input_semantics", "output_semantics", "source_kind", "provenance_sha256"}
    _object(usage, allowed, allowed)
    if usage["input_semantics"] not in {"includes_cache", "excludes_cache"}:
        _fail("unsupported_input_semantics")
    if usage["output_semantics"] != "includes_reasoning":
        _fail("unsupported_output_semantics")
    if usage["source_kind"] not in {"provider_reported", "synthetic"}:
        _fail("unsupported_usage_source")
    _hash(usage["provenance_sha256"])
    values = {key: _number(usage[key], integer=True) for key in TOKEN_KEYS}
    cache = [values["cache_read_tokens"], values["cache_write_tokens"]]
    incoming, outgoing = values["input_tokens"], values["output_tokens"]
    raw_input = incoming
    if usage["input_semantics"] == "excludes_cache":
        uncached = incoming
        incoming = None if incoming is None or None in cache else incoming + sum(cache)
    else:
        uncached = None if incoming is None or None in cache else incoming - sum(cache)
        if uncached is not None and uncached < 0:
            _fail("inconsistent_cache_usage")
        for bucket in cache:
            if bucket is not None and incoming is not None and bucket > incoming:
                _fail("inconsistent_cache_usage")
    reasoning = values["reasoning_tokens"]
    if outgoing is not None and reasoning is not None and reasoning > outgoing:
        _fail("inconsistent_reasoning_usage")
    reported = values["total_tokens"]
    calculated = None if incoming is None or outgoing is None else incoming + outgoing
    if reported is not None and calculated is not None and reported != calculated:
        _fail("inconsistent_total_usage")
    if reported is not None and any(v is not None and v > reported for v in (incoming, outgoing)):
        _fail("inconsistent_total_usage")
    cache_lower = sum(v for v in cache if v is not None)
    input_lower = ((raw_input or 0) + cache_lower if usage["input_semantics"] == "excludes_cache"
                   else max(raw_input or 0, cache_lower))
    output_lower = max(outgoing or 0, reasoning or 0)
    if reported is not None and input_lower + output_lower > reported:
        _fail("inconsistent_total_usage")
    values.update(input_tokens=incoming, uncached_input_tokens=uncached,
                  total_tokens=reported if reported is not None else calculated,
                  provider_reported_total=reported, source_kind=usage["source_kind"],
                  provenance_sha256=usage["provenance_sha256"])
    return values


def estimate_cost(usage, pricing):
    """Explicit per-million rates; no network price lookup or implied billed charge."""
    keys = {"currency", "price_sha256", "uncached_input_per_million", "cache_read_per_million",
            "cache_write_per_million", "output_per_million"}
    _object(pricing, keys, keys)
    if not isinstance(pricing["currency"], str) or not re.fullmatch(r"[A-Z]{3}", pricing["currency"]):
        _fail("invalid_currency")
    _hash(pricing["price_sha256"])
    normalized = normalize_usage(usage)
    fields = ("uncached_input", "cache_read", "cache_write", "output")
    amount = Decimal(0)
    for field in fields:
        rate = _number(pricing[field + "_per_million"], nullable=False)
        count = normalized[field + "_tokens"]
        if count is None:
            return None
        amount += Decimal(count) * Decimal(str(rate)) / Decimal(1_000_000)
    return {"amount": float(amount), "currency": pricing["currency"],
            "source_kind": "estimated", "basis_sha256": pricing["price_sha256"]}


def _money(value, source):
    if value is None:
        return None
    _object(value, {"amount", "currency", "source_kind", "basis_sha256"},
            {"amount", "currency", "source_kind", "basis_sha256"})
    _number(value["amount"], nullable=False)
    _hash(value["basis_sha256"])
    if value["source_kind"] != source or not isinstance(value["currency"], str) or not re.fullmatch(r"[A-Z]{3}", value["currency"]):
        _fail("invalid_cost_basis")
    return value


def _metric(values, complete, source):
    known = [v for v in values if v is not None]
    total = (sum(known) if all(type(v) is int for v in known)
             else float(sum((Decimal(str(v)) for v in known), Decimal(0))))
    return {"value": total if complete and len(known) == len(values) else None,
            "known_sum": total if known or complete and not values else None,
            "known_records": len(known), "observed_records": len(values),
            "coverage": "complete" if complete and len(known) == len(values) else "partial" if known else "unknown",
            "source_kind": source}


def _validate_run(run):
    keys = {"format", "source_kind", "condition", "identity", "comparison", "configuration", "coverage",
            "requests", "tools", "measurements", "outcome", "answer_sha256", "observation_sha256", "trial_order"}
    _object(run, keys | {"guidance"}, keys)
    if run["format"] != "efficiency-run/1" or run["source_kind"] not in {"synthetic", "captured"}:
        _fail("unsupported_run_format")
    if run["condition"] not in {"disabled", "enabled"} or run["outcome"] not in STATES - {"started"}:
        _fail("invalid_run_state")
    _hash(run["answer_sha256"], nullable=True)
    _hash(run["observation_sha256"], nullable=True)
    _number(run["trial_order"], integer=True)
    if run["trial_order"] == 0:
        _fail("invalid_trial_order")
    if run.get("guidance") is not None:
        fields = {"preview_sha256", "policy_sha256", "bio_sha256", "selected_configuration_sha256", "recorded_before_execution"}
        guidance = _object(run["guidance"], fields, fields)
        for key in fields - {"recorded_before_execution"}:
            _hash(guidance[key])
        if type(guidance["recorded_before_execution"]) is not bool:
            _fail("invalid_guidance")
    identity_keys = {"task_id", "pair_id", "repetition", "task_sha256", "input_sha256", "corpus_sha256", "rubric_sha256"}
    identity = _object(run["identity"], identity_keys, identity_keys)
    _label(identity["task_id"])
    _label(identity["pair_id"])
    _number(identity["repetition"], integer=True, nullable=False)
    for key in identity_keys - {"task_id", "pair_id", "repetition"}:
        _hash(identity[key])
    comparison = _object(run["comparison"], {"system", "allowed_differences"}, {"system", "allowed_differences"})
    if comparison["system"] not in {"kre", "gcb"} or not isinstance(comparison["allowed_differences"], list):
        _fail("invalid_comparison")
    allowed = comparison["allowed_differences"]
    if len(allowed) != len(set(allowed)) or set(allowed) - {"provider", "model", "model_revision", "reasoning_sha256"}:
        _fail("invalid_comparison")
    if comparison["system"] == "kre" and allowed:
        _fail("invalid_comparison")
    config_keys = {"provider", "model", "model_revision", "reasoning_sha256", "tools", "permissions_sha256",
                   "environment_sha256", "history_sha256", "source_access_sha256", "retry_policy_sha256", "cache_state", "warm_state", "memory_state"}
    config = _object(run["configuration"], config_keys, config_keys)
    for key in ("provider", "model"):
        _label(config[key])
    if config["model_revision"] is not None:
        _label(config["model_revision"])
    for key in config_keys:
        if key.endswith("_sha256"):
            _hash(config[key], nullable=key == "history_sha256")
    if not isinstance(config["tools"], list) or len(config["tools"]) > 100 or len(config["tools"]) != len(set(config["tools"])):
        _fail("invalid_tools")
    for name in config["tools"]:
        _label(name)
    if config["cache_state"] not in {"cold", "warm", "mixed", "unknown"} or config["warm_state"] not in {"cold", "warm", "mixed", "unknown"}:
        _fail("invalid_environment_state")
    if config["memory_state"] not in {"isolated", "unknown", "contaminated"}:
        _fail("invalid_environment_state")
    coverage = _object(run["coverage"], {"requests", "auxiliary", "tools", "context"}, {"requests", "auxiliary", "tools", "context"})
    if any(v not in COVERAGE for v in coverage.values()):
        _fail("invalid_coverage")
    _object(run["measurements"], TIME_KEYS, TIME_KEYS)
    for key, value in run["measurements"].items():
        _number(value, integer=key == "storage_bytes")
    for key in ("requests", "tools"):
        if not isinstance(run[key], list) or len(run[key]) > MAX_RECORDS:
            _fail("record_limit")


def _requests(run):
    records = {}
    allowed = {"id", "state", "retry_of", "usage", "context", "actual_cost", "estimated_cost", "configuration_sha256"}
    for row in run["requests"]:
        _object(row, allowed, allowed)
        _label(row["id"])
        _hash(row["configuration_sha256"], nullable=True)
        if row["state"] not in STATES:
            _fail("invalid_request_state")
        if row["retry_of"] is not None:
            _label(row["retry_of"])
            if row["retry_of"] == row["id"]:
                _fail("invalid_retry")
        normalized = normalize_usage(row["usage"])
        if run["source_kind"] == "captured" and normalized["source_kind"] == "synthetic":
            _fail("mixed_evidence_kind")
        _object(row["context"], set(CONTEXT_KEYS) | {"input_sha256"}, set(CONTEXT_KEYS) | {"input_sha256"})
        for key in CONTEXT_KEYS:
            _number(row["context"][key], integer=True)
        _hash(row["context"]["input_sha256"], nullable=True)
        _money(row["actual_cost"], "provider_billed")
        _money(row["estimated_cost"], "estimated")
        previous = records.get(row["id"])
        if previous is not None:
            if previous == row:
                continue
            pending, terminal = (previous, row) if previous["state"] == "started" else (row, previous)
            if (pending["state"] != "started" or terminal["state"] == "started"
                    or pending["retry_of"] != terminal["retry_of"]
                    or pending["configuration_sha256"] is not None and pending["configuration_sha256"] != terminal["configuration_sha256"]
                    or pending["usage"] is not None or pending["actual_cost"] is not None or pending["estimated_cost"] is not None):
                _fail("conflicting_request_receipt")
            for key, value in pending["context"].items():
                if value is not None and value != terminal["context"][key]:
                    _fail("conflicting_request_receipt")
            row = terminal
        records[row["id"]] = row
    if run["coverage"]["requests"] == "complete":
        for row in records.values():
            if row["retry_of"] is not None and row["retry_of"] not in records:
                _fail("missing_retry_origin")
    for row in records.values():
        seen, current = set(), row
        while current is not None:
            if current["id"] in seen:
                _fail("invalid_retry_cycle")
            seen.add(current["id"])
            current = records.get(current["retry_of"])
    return list(records.values())


def summarize_run(run):
    _validate_run(run)
    requests = _requests(run)
    complete = run["coverage"]["requests"] == run["coverage"]["auxiliary"] == "complete"
    usage = [normalize_usage(r["usage"]) for r in requests]
    metrics = {key: _metric([u[key] for u in usage], complete, "provider_reported" if run["source_kind"] == "captured" else "synthetic")
               for key in TOKEN_KEYS + ("uncached_input_tokens", "provider_reported_total")}
    metrics["model_requests"] = _metric([1 for _ in requests], complete, "observed_request_ledger")
    context_complete = complete and run["coverage"]["context"] == "complete"
    for key in CONTEXT_KEYS:
        metrics[key] = _metric([r["context"][key] for r in requests], context_complete,
                               "local_estimate" if key == "estimated_input_tokens" else "boundary_measured")
    money_bases = {}
    for key in ("actual_cost", "estimated_cost"):
        entries = [r[key] for r in requests]
        currencies = {x["currency"] for x in entries if x is not None}
        if len(currencies) > 1:
            _fail("mixed_currency")
        metrics[key] = _metric([x["amount"] if x is not None else None for x in entries], complete,
                               "provider_billed" if key == "actual_cost" else "local_estimate")
        money_bases[key] = {"currency": next(iter(currencies), None),
                            "basis_sha256": sorted({x["basis_sha256"] for x in entries if x is not None})}
    tools = {}
    for tool in run["tools"]:
        keys = {"id", "name", "state", "response_bytes", "response_sha256", "elapsed_seconds"}
        _object(tool, keys, keys)
        _label(tool["id"])
        _label(tool["name"])
        if tool["state"] not in STATES:
            _fail("invalid_tool_state")
        _number(tool["response_bytes"], integer=True)
        _number(tool["elapsed_seconds"])
        _hash(tool["response_sha256"], nullable=True)
        if tool["id"] in tools and tool != tools[tool["id"]]:
            _fail("conflicting_tool_receipt")
        tools[tool["id"]] = tool
    tool_complete = run["coverage"]["tools"] == "complete"
    metrics["tool_calls"] = _metric([1 for _ in tools], tool_complete, "host_recorded")
    metrics["tool_response_bytes"] = _metric([t["response_bytes"] for t in tools.values()], tool_complete, "boundary_measured")
    metrics["tool_elapsed_seconds"] = _metric([t["elapsed_seconds"] for t in tools.values()], tool_complete, "local_measured")
    for key, value in run["measurements"].items():
        metrics[key] = _metric([value], True, "local_measured")
    terminal = (all(r["state"] not in {"started", "incomplete"} for r in requests + list(tools.values()))
                and run["outcome"] != "incomplete")
    if not terminal:
        # Intermediate receipts are observed subtotals, never final workflow totals.
        for metric in metrics.values():
            metric["value"] = None
            metric["coverage"] = "partial" if metric["known_records"] else "unknown"
            if not metric["known_records"]:
                metric["known_sum"] = None
    counts = {state: sum(r["state"] == state for r in requests) for state in sorted(STATES)}
    return {"format": "efficiency-summary/1", "source_kind": run["source_kind"],
            "run_sha256": fingerprint(run), "identity": deepcopy(run["identity"]),
            "condition": run["condition"], "configuration": deepcopy(run["configuration"]),
            "coverage": deepcopy(run["coverage"]), "outcome": run["outcome"], "answer_sha256": run["answer_sha256"],
            "observation_sha256": run["observation_sha256"], "trial_order": run["trial_order"],
            "execution_terminal": terminal,
            "main_model_configuration_sha256": model_configuration_sha256(run["configuration"]),
            "request_configurations": {key: sum(r["configuration_sha256"] == key for r in requests)
                                       for key in sorted({r["configuration_sha256"] for r in requests if r["configuration_sha256"] is not None})},
            "unknown_request_configurations": sum(r["configuration_sha256"] is None for r in requests),
            "guidance": deepcopy(run.get("guidance")),
            "metrics": metrics, "cost_bases": money_bases,
            "attempt_outcomes": counts, "observed_retries": sum(r["retry_of"] is not None for r in requests),
            "tool_counts": {name: sum(t["name"] == name for t in tools.values()) for name in sorted({t["name"] for t in tools.values()})},
            "limits": ["Completeness is a collector assertion, not discovered by this importer.",
                       "No raw prompts, tool contents, request IDs or exception bodies are exported.",
                       "Context bytes and local token estimates are not provider token consumption."]}


def change(before, after, quality=False):
    if before is None or after is None:
        return {"absolute": None, "percent": None, "direction": "unknown"}
    difference = after - before
    percent = None if before == 0 else (before - after) / before * 100
    return {"absolute": difference, "percent": difference * 100 if quality else percent,
            "direction": "unchanged" if difference == 0 else "improvement" if (difference > 0 if quality else difference < 0) else "regression"}


def _quality(score, run):
    if score is None:
        return None
    if not isinstance(score, dict) or score.get("format") != "quality-score/1":
        _fail("invalid_quality_score")
    for key in ("task_sha256", "rubric_sha256"):
        if score.get(key) != run["identity"][key]:
            _fail("quality_identity_mismatch")
    if score.get("task_id") != run["identity"]["task_id"] or score.get("answer_sha256") != run["answer_sha256"]:
        _fail("quality_answer_mismatch")
    if run["observation_sha256"] is None or score.get("observation_sha256") != run["observation_sha256"]:
        _fail("quality_observation_mismatch")
    for key in ("quality_pass", "critical_pass", "completion_pass"):
        if score.get(key) is not None and type(score[key]) is not bool:
            _fail("invalid_quality_score")
    result = {key: score.get(key) for key in ("quality_pass", "critical_pass", "completion_pass")}
    for key in ("citation_exactness", "citation_support", "evidence_recall", "evidence_validity"):
        measure = score.get(key)
        if not isinstance(measure, dict):
            _fail("invalid_quality_score")
        passed, total, unknown, value = measure.get("passed"), measure.get("total"), measure.get("unknown", 0), measure.get("score")
        _number(passed, integer=True)
        _number(total, integer=True)
        _number(unknown, integer=True)
        _number(value)
        counts = (passed, total, unknown)
        if any(x is None for x in counts) and not all(x is None for x in counts):
            _fail("invalid_quality_score")
        if passed is not None and total is not None and passed + unknown > total:
            _fail("invalid_quality_score")
        expected = None if passed is None or total in (None, 0) or unknown else passed / total
        if value != expected:
            _fail("invalid_quality_score")
        result[key] = {"passed": passed, "total": total, "unknown": unknown, "score": value}
    if result["quality_pass"] is True and (run["answer_sha256"] is None or result["critical_pass"] is not True or result["completion_pass"] is not True
            or any(result[key]["unknown"] or result[key]["score"] is not None and result[key]["score"] < 1
                   for key in ("citation_exactness", "citation_support", "evidence_recall", "evidence_validity"))):
        _fail("inconsistent_quality_score")
    return result


def compare_runs(disabled, enabled, *, quality_disabled=None, quality_enabled=None):
    before, after = summarize_run(disabled), summarize_run(enabled)
    if disabled["condition"] != "disabled" or enabled["condition"] != "enabled":
        _fail("condition_order_mismatch")
    if disabled["identity"] != enabled["identity"] or disabled["comparison"] != enabled["comparison"]:
        _fail("pair_identity_mismatch")
    if disabled["source_kind"] != enabled["source_kind"]:
        _fail("mixed_evidence_kind")
    issues, differences = [], {}
    if disabled["trial_order"] is None or enabled["trial_order"] is None or disabled["trial_order"] == enabled["trial_order"]:
        issues.append("trial_order_unknown")
    allowed = set(disabled["comparison"]["allowed_differences"])
    for key, value in disabled["configuration"].items():
        other = enabled["configuration"][key]
        if key == "tools":
            permitted = {"kre_retrieve", "kre_validate"} if disabled["comparison"]["system"] == "kre" else {"gcb_recommend"}
            if not set(value) <= set(other) or (set(other) - set(value)) - permitted:
                issues.append("tools_differ_materially")
            if set(value) & permitted:
                issues.append("treatment_present_in_disabled_arm")
            if disabled["comparison"]["system"] == "kre" and not permitted <= set(other):
                issues.append("kre_treatment_unavailable")
        elif value != other:
            differences[key] = {"disabled": value, "enabled": other, "predeclared": key in allowed}
            if key not in allowed:
                issues.append("unmatched_" + key)
    for config in (disabled["configuration"], enabled["configuration"]):
        if config["history_sha256"] is None:
            issues.append("history_unknown")
        if config["memory_state"] != "isolated":
            issues.append("memory_" + config["memory_state"])
        for key in ("cache_state", "warm_state"):
            if config[key] in {"unknown", "mixed"}:
                issues.append(key + "_uncontrolled")
    for side in (before, after):
        if side["configuration"]["model_revision"] is None:
            issues.append("model_revision_unknown")
        if side["unknown_request_configurations"]:
            issues.append("request_configuration_unknown")
        if set(side["request_configurations"]) - {side["main_model_configuration_sha256"]}:
            issues.append("request_configuration_deviation")
    if disabled["comparison"]["system"] == "gcb":
        guidance = enabled.get("guidance")
        if (guidance is None or guidance["recorded_before_execution"] is not True
                or guidance["selected_configuration_sha256"] != after["main_model_configuration_sha256"]):
            issues.append("gcb_guidance_unverified")
    qb, qa = _quality(quality_disabled, disabled), _quality(quality_enabled, enabled)
    quality_ok = (before["outcome"] == after["outcome"] == "completed"
                  and all(q is not None and q["quality_pass"] is True and q["critical_pass"] is True and q["completion_pass"] is True for q in (qb, qa)))
    rows = []
    for name in before["metrics"]:
        left, right = before["metrics"][name]["value"], after["metrics"][name]["value"]
        comparable = True
        if name in ("actual_cost", "estimated_cost"):
            lb, rb = before["cost_bases"][name], after["cost_bases"][name]
            if lb["currency"] != rb["currency"]:
                comparable = False
            # Merely permitting a model difference cannot justify changing its price.
            different_model = any(key in allowed and key in differences
                                  for key in ("provider", "model", "model_revision"))
            if name == "estimated_cost" and lb["basis_sha256"] != rb["basis_sha256"] and not different_model:
                comparable = False
        rows.append({"metric": name, "disabled": left, "enabled": right,
                     "change": change(left, right) if comparable else change(None, None),
                     "comparable": comparable, "source_kind": before["metrics"][name]["source_kind"]})
    for name in ("quality_pass", "citation_exactness", "citation_support", "evidence_recall", "evidence_validity"):
        vals = []
        for q in (qb, qa):
            vals.append(None if q is None else (None if q[name] is None else int(q[name])) if name == "quality_pass" else q[name]["score"])
        rows.append({"metric": name, "disabled": vals[0], "enabled": vals[1], "change": change(*vals, quality=True),
                     "comparable": True, "source_kind": "quality_score", "change_unit": "percentage_points"})
    complete = all(side["coverage"]["requests"] == side["coverage"]["auxiliary"] == "complete"
                   and side["execution_terminal"] for side in (before, after))
    claims = {}
    for name in ("total_tokens", "actual_cost", "estimated_cost", "completion_seconds"):
        row = next(r for r in rows if r["metric"] == name)
        claims[name] = ("synthetic_only" if disabled["source_kind"] == "synthetic" else
                        "not_demonstrated" if issues or not quality_ok or not complete or not row["comparable"] or row["change"]["percent"] is None else
                        "improvement" if row["change"]["percent"] > 0 else "regression" if row["change"]["percent"] < 0 else "no_change")
    return {"format": "efficiency-comparison/1", "source_kind": disabled["source_kind"],
            "identity": deepcopy(disabled["identity"]), "system": disabled["comparison"]["system"],
            "controlled": not issues, "control_limitations": sorted(set(issues)),
            "declared_configuration_differences": differences, "quality_preserved": quality_ok,
            "all_request_coverage": complete, "rows": rows, "claims": claims,
            "disabled": before, "enabled": after, "quality_disabled": qb, "quality_enabled": qa}


def render_markdown(report):
    if not isinstance(report, dict) or report.get("format") != "efficiency-comparison/1":
        _fail("invalid_report")
    lines = ["# Paired efficiency report", "", "Evidence: **" + report["source_kind"] + "**."]
    if report["source_kind"] == "synthetic":
        lines += ["Synthetic verification only; no real workflow savings demonstrated."]
    for arm in ("disabled", "enabled"):
        config = report[arm]["configuration"]
        lines += [arm.title() + " model: " + config["provider"] + "/" + config["model"] + "; requested reasoning fingerprint: `" + config["reasoning_sha256"] + "`."]
    for key in ("actual_cost", "estimated_cost"):
        lines += [key + " currency (disabled / enabled): " + str(report["disabled"]["cost_bases"][key]["currency"]) + " / " + str(report["enabled"]["cost_bases"][key]["currency"]) + "."]
    lines += ["", "Controlled conditions: " + str(report["controlled"]).lower() + ". Quality preserved: " + str(report["quality_preserved"]).lower() + ".",
              "Arithmetic reductions below are not savings claims; qualified claims appear after the table.",
              "", "| Metric | Disabled | Enabled | Change |", "|---|---:|---:|---:|"]
    def show(value):
        return "unknown" if value is None else format(value, ".8g")
    for row in report["rows"]:
        unit = " pp" if row.get("change_unit") == "percentage_points" else "% reduction"
        difference = "N/A" if row["change"]["percent"] is None else show(row["change"]["percent"]) + unit
        if row["change"]["direction"] == "regression":
            difference += " (regression)"
        lines.append("| " + row["metric"] + " | " + show(row["disabled"]) + " | " + show(row["enabled"]) + " | " + difference + " |")
    lines += ["", "Qualified claims: " + "; ".join(key + "=" + value for key, value in report["claims"].items()) + ".",
              "Coverage (disabled / enabled): " + "; ".join(key + "=" + report["disabled"]["metrics"][key]["coverage"] + " / " + report["enabled"]["metrics"][key]["coverage"] for key in report["claims"]) + ".",
              "Context bytes, estimated tokens, billed charges and estimated costs are separate measures.",
              "All observed attempts are retained; unknown coverage blocks whole-workflow claims."]
    if report["control_limitations"]:
        lines += ["", "Control limitations: " + ", ".join(report["control_limitations"]) + "."]
    return "\n".join(lines) + "\n"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "measurement: invalid arguments; use --help\n")


def main(argv=None):
    parser = _Parser(description="Offline metadata accounting; never contacts a model or Gateway.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    summarize = commands.add_parser("summarize")
    summarize.add_argument("run")
    compare = commands.add_parser("compare")
    compare.add_argument("disabled")
    compare.add_argument("enabled")
    compare.add_argument("--quality-disabled")
    compare.add_argument("--quality-enabled")
    compare.add_argument("--format", choices=["json", "markdown"], default="json")
    score = commands.add_parser("score")
    score.add_argument("rubric")
    score.add_argument("observation")
    score.add_argument("--sources")
    output = commands.add_parser("check-output", help="Check raw JSON and exact citations; never repairs answers")
    output.add_argument("raw_output")
    output.add_argument("rubric")
    output.add_argument("--sources", required=True)
    output.add_argument("--evidence", required=True)
    output.add_argument("--known-unsupported")
    try:
        args = parser.parse_args(argv)
        if args.command == "summarize":
            result = summarize_run(load_json(args.run))
        elif args.command == "compare":
            result = compare_runs(load_json(args.disabled), load_json(args.enabled),
                                  quality_disabled=load_json(args.quality_disabled) if args.quality_disabled else None,
                                  quality_enabled=load_json(args.quality_enabled) if args.quality_enabled else None)
            if args.format == "markdown":
                print(render_markdown(result), end="")
                return 0
        elif args.command == "check-output":
            from .output_validation import validate_output
            with Path(args.raw_output).open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1).decode("utf-8")
            result = validate_output(raw, load_json(args.rubric),
                                     sources=load_json(args.sources), evidence=load_json(args.evidence),
                                     known_unsupported_sentences=load_json(args.known_unsupported) if args.known_unsupported else ())
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            return 0 if result["mechanical_gate"] is True and result["end_to_end_quality_pass"] is not False else 1
        else:
            from .quality import score_trial
            result = score_trial(load_json(args.rubric), load_json(args.observation),
                                 load_json(args.sources) if args.sources else None)
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, TypeError, OSError, RecursionError, UnicodeError):
        print("measurement: invalid input or unsupported measurement", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
