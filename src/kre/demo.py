"""Fictional K2 lifecycle and continuity demonstration; no network or models."""
import uuid

from .store import evidence_ref


def run_demo(store, *, collection):
    # Unique IDs let repeated demos leave prior immutable history intact.
    prefix = "demo-k2-" + uuid.uuid4().hex[:8]
    old = prefix + "-old"
    current = prefix + "-guide"
    text1 = "# Fictional rollout\n\nRollback uses the amber snapshot.\n"
    text2 = "# Fictional rollout\n\nRollback uses the blue snapshot.\n"
    noise = "# Fictional cafeteria\n\nLunch includes lentils and pears.\n"
    request = {"contract_version": "0.1", "request_id": prefix, "query": "rollback",
               "access_scope_ref": "local", "destination": "local_only", "purpose": "current_answer",
               "source_ids": [current, old, prefix + "-irrelevant"],
               "budget": {"max_tokens": 8000, "max_bytes": 8000, "max_items": 8}}
    r1 = store.ingest_text(current, text1, collection=collection)
    initial = store.context(request)
    r2 = store.ingest_text(current, text2, collection=collection)
    after_update_validation = store.validate_context(initial, scope_ref="local", destination="local_only")
    store.ingest_text(old, "Legacy rollback uses the red snapshot.", collection=collection)
    store.ingest_text(prefix + "-irrelevant", noise, collection=collection)
    store.update_policy(current, freshness="fresh")
    before = store.context(request)
    obsolete = next(item for item in before["items"] if item["source_id"] == old)
    kept = next(item for item in before["items"] if item["source_id"] == current)
    assertion = lambda text: {"text": text, "origin": "user_assertion", "refs": []}
    card = {"objective": assertion("Prepare a fictional rollback review."),
            "constraints": [assertion("Keep this demonstration offline.")],
            "decisions": [{"text": item["text"], "origin": "source_evidence", "refs": [evidence_ref(item)]}
                          for item in (kept, obsolete)],
            "questions": [assertion("Has the operator approved the rollback?")],
            "next_actions": [assertion("Ask the operator before any actual action.")]}
    checkpoint = store.checkpoint_task(prefix, scope_ref="local", card=card)
    store.revoke(old)
    after = store.context(request)
    resumed = store.resume_task(prefix, scope_ref="local")
    required = store.context_required(request, required_refs=[evidence_ref(kept)])
    missing = store.context_required(request, required_refs=[evidence_ref(obsolete)])
    # Simple baseline: every currently eligible chunk from this demo, rendered with
    # identical citation overhead. This is a size illustration, not a quality test.
    all_rows = store.db.execute("""SELECT c.*,r.source_id,r.recorded_at,r.lifecycle,s.authority,s.origin,s.freshness,s.egress
        FROM chunks c JOIN revisions r ON c.revision_id=r.revision_id JOIN sources s ON s.source_id=r.source_id
        WHERE s.source_id IN (?,?,?) AND s.state='active' AND r.lifecycle='active' AND s.freshness!='stale'
        ORDER BY c.id""", (current, old, prefix + "-irrelevant")).fetchall()
    baseline = store._render([store._item(row, f"E{i+1}") for i, row in enumerate(all_rows)])
    return {"demo": "K2 synthetic local evidence, no model or network", "first_revision": r1, "current_revision": r2,
            "initial_context": initial, "initial_context_validation_after_update": after_update_validation,
            "prior_revision_lifecycle": store.revision(r1, scope_ref="local")["lifecycle"],
            "before_revocation": before, "after_revocation": after, "checkpoint": checkpoint, "resume": resumed,
            "required_current": required, "required_revoked": missing,
            "context_size_comparison": {"retrieved_bytes": after["token_usage"]["context_bytes"],
                                        "all_current_demo_chunks_bytes": len(baseline.encode("utf-8")),
                                        "method": "same eligible demo corpus and citation rendering; baseline includes irrelevant chunks",
                                        "limitation": "size illustration only; use scripts/evaluate.py for budget-matched quality comparison"}}
