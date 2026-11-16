"""Bounded, deterministic task cards. No summarizer and no inferred dependencies."""
from __future__ import annotations

import json

from .store import _hash, _identifier, _now, _valid_refs

SECTIONS = ("objective", "constraints", "decisions", "questions", "next_actions")
MAX_CARD_BYTES = 32768
MAX_RESUME_BYTES = 131072


def _entries(card):
    for section in SECTIONS:
        values = [card[section]] if section == "objective" else card[section]
        for index, entry in enumerate(values):
            yield section, index, entry


def _validate_card(card):
    if not isinstance(card, dict) or set(card) != set(SECTIONS):
        raise ValueError("Task card requires objective, constraints, decisions, questions and next_actions")
    if any(not isinstance(card[key], list) or len(card[key]) > 16 for key in SECTIONS[1:]):
        raise ValueError("Task lists must contain at most 16 entries each")
    refs = []
    for _, _, entry in _entries(card):
        if not isinstance(entry, dict) or set(entry) != {"text", "origin", "refs"}:
            raise ValueError("Each task entry requires text, origin and refs")
        text = entry["text"]
        if not isinstance(text, str) or not 1 <= len(text.encode("utf-8")) <= 8192 or "\x00" in text:
            raise ValueError("Task entry text must contain 1–8192 UTF-8 bytes without NUL")
        if entry["origin"] not in ("user_assertion", "source_evidence", "model_inference"):
            raise ValueError("Invalid task origin")
        if not _valid_refs(entry["refs"]) or len(entry["refs"]) > 8:
            raise ValueError("Task entry requires at most eight exact unique references")
        if entry["origin"] != "user_assertion" and not entry["refs"]:
            raise ValueError("Evidence and inference entries require explicit dependencies")
        for ref in entry["refs"]:
            if ref not in refs:
                refs.append(ref)
    if len(refs) > 32:
        raise ValueError("Task card has more than 32 distinct dependencies")
    encoded = json.dumps(card, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_CARD_BYTES:
        raise ValueError("Task card exceeds 32 KiB; checkpoint rejected without truncation")
    return encoded, refs


def _request(scope_ref):
    return {"access_scope_ref": scope_ref, "purpose": "current_answer", "destination": "local_only"}


def checkpoint_task(store, task_id, *, scope_ref, card):
    if not _identifier(task_id) or not isinstance(scope_ref, str) or scope_ref not in store.scopes:
        raise ValueError("Invalid task binding")
    encoded, refs = _validate_card(card)
    with store.db:
        store.db.execute("BEGIN IMMEDIATE")
        existing = store.db.execute("SELECT * FROM task_cards WHERE task_id=?", (task_id,)).fetchone()
        if existing and (existing["principal"], existing["scope_ref"]) != (store.principal, scope_ref):
            raise PermissionError("Task unavailable in caller binding")
        rows = {json.dumps(ref, sort_keys=True): store._eligible_ref(ref, _request(scope_ref)) for ref in refs}
        if any(row is None for row in rows.values()):
            raise ValueError("Task dependencies unavailable; checkpoint rejected without truncation")
        for _, _, entry in _entries(card):
            if entry["origin"] == "source_evidence":
                if any(rows[json.dumps(ref, sort_keys=True)]["origin"] != "source_evidence" for ref in entry["refs"]):
                    raise ValueError("Derived source origins cannot be promoted to source evidence")
                exact = "\n\n".join(rows[json.dumps(ref, sort_keys=True)]["text"] for ref in entry["refs"])
                if entry["text"] != exact:
                    raise ValueError("Evidence task text must be exact referenced excerpts in reference order")
        evidence = [store._item(row, f"E{i + 1}") for i, row in enumerate(rows.values())]
        if len(json.dumps({"card": card, "evidence": evidence}, ensure_ascii=False).encode("utf-8")) > MAX_RESUME_BYTES - 2048:
            raise ValueError("Task and evidence exceed bounded resume size; checkpoint rejected")
        changed = not existing or existing["card_json"] != encoded
        if changed:
            store.db.execute("INSERT OR REPLACE INTO task_cards VALUES (?,?,?,?,?)",
                             (task_id, store.principal, scope_ref, encoded, _now()))
            store._changed()
        return {"task_version": "kre-task/1", "task_id": task_id, "status": "checkpointed",
                "changed": changed, "card_sha256": _hash(encoded), "context_revision": store._generation()}


def resume_task(store, task_id, *, scope_ref):
    if not _identifier(task_id) or not isinstance(scope_ref, str) or scope_ref not in store.scopes:
        raise PermissionError("Task unavailable in caller binding")
    with store.db:
        store.db.execute("BEGIN")
        saved = store.db.execute("SELECT * FROM task_cards WHERE task_id=? AND principal=? AND scope_ref=?",
                                 (task_id, store.principal, scope_ref)).fetchone()
        if not saved:
            raise PermissionError("Task unavailable in caller binding")
        card = json.loads(saved["card_json"])
        _, refs = _validate_card(card)
        rows = {json.dumps(ref, sort_keys=True): store._eligible_ref(ref, _request(scope_ref)) for ref in refs}
        resumed = {key: None if key == "objective" else [] for key in SECTIONS}
        invalidated = []
        retained_refs = []
        for section, index, entry in _entries(card):
            live = all(rows[json.dumps(ref, sort_keys=True)] is not None for ref in entry["refs"])
            if live and entry["origin"] == "source_evidence":
                exact = "\n\n".join(rows[json.dumps(ref, sort_keys=True)]["text"] for ref in entry["refs"])
                live = entry["text"] == exact and all(rows[json.dumps(ref, sort_keys=True)]["origin"] == "source_evidence" for ref in entry["refs"])
            if not live:
                # Do not return dependent prose, even as a warning or user assertion.
                invalidated.append({"section": section, "index": index, "reason": "evidence_unavailable"})
                continue
            if section == "objective":
                resumed[section] = entry
            else:
                resumed[section].append(entry)
            for ref in entry["refs"]:
                if ref not in retained_refs:
                    retained_refs.append(ref)
        evidence = [store._item(rows[json.dumps(ref, sort_keys=True)], f"E{i + 1}") for i, ref in enumerate(retained_refs)]
        result = {"task_version": "kre-task/1", "task_id": task_id,
                  "status": "partial" if invalidated else "ok", "card": resumed,
                  "evidence": evidence, "invalidated": invalidated, "recorded_at": saved["recorded_at"],
                  "card_sha256": _hash(saved["card_json"]), "context_revision": store._generation(),
                  "scope_fingerprint": store._fingerprint(scope_ref),
                  "warnings": ["USER_ASSERTIONS_AND_MODEL_INFERENCES_ARE_UNVERIFIED", "SNAPSHOT_ONLY_REVALIDATE_BEFORE_USE"]}
        size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        if size > MAX_RESUME_BYTES:
            raise ValueError("Resume exceeds 128 KiB; no partial truncation applied")
        return result
