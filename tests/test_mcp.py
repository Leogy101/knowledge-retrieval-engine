"""Independent adapter boundary tests; synthetic state and no harness/provider."""
import copy
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from kre import Store, evidence_ref
from kre import _stdio
from kre.mcp import KnowledgeTools, main


def rpc(identifier, method, params=None):
    message = {"jsonrpc": "2.0", "id": identifier, "method": method}
    if params is not None:
        message["params"] = params
    return message


def initialization(identifier=1):
    return rpc(identifier, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                           "clientInfo": {"name": "synthetic-test", "version": "1"}})


def wire(messages):
    return b"".join(json.dumps(message).encode() + b"\n" for message in messages)


def transport(raw, definitions, call):
    outgoing = io.BytesIO()
    code = _stdio.serve("kre", "test", definitions, call, incoming=io.BytesIO(raw), outgoing=outgoing)
    return code, [json.loads(line) for line in outgoing.getvalue().splitlines()], outgoing.getvalue()


class KnowledgeToolTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:", principal="operator-owned-domain",
                           scopes={"pilot": {"shared"}, "operator": {"shared", "private"}},
                           destinations=frozenset({"local_only", "approved_remote"}))
        self.addCleanup(self.store.close)
        self.store.ingest_text("public", "Quartz approved synthetic port is 8042.", collection="shared", egress="approved_remote")
        self.store.ingest_text("private", "PRIVATE_SENTINEL quartz quartz quartz secret.", collection="private", egress="approved_remote")
        self.store.ingest_text("local", "LOCAL_SENTINEL cobalt local evidence.", collection="shared", egress="local_only")
        self.handler = KnowledgeTools(self.store, scope_ref="pilot", destination="approved_remote", max_bytes=1600)

    def item(self, source):
        request = {"contract_version": "0.1", "request_id": "trusted-fixture", "query": "quartz cobalt",
                   "access_scope_ref": "operator", "destination": "local_only", "purpose": "current_answer",
                   "source_ids": [source], "budget": {"max_tokens": 3000, "max_items": 3, "max_bytes": 3000}}
        return self.store.context(request)["items"][0]

    def test_remote_tools_use_fixed_scope_and_preserve_exact_provenance(self):
        definitions = self.handler.definitions()
        self.assertEqual({tool["name"] for tool in definitions}, {"kre_retrieve", "kre_validate"})
        self.assertTrue(all(tool["inputSchema"]["additionalProperties"] is False for tool in definitions))
        response = self.handler.call("kre_retrieve", {"query": "quartz", "max_items": 1})
        self.assertIsNone(response["error"])
        item = response["context"]["items"][0]
        self.assertEqual(item["source_id"], "public")
        self.assertEqual(item["text"], "Quartz approved synthetic port is 8042.")
        self.assertEqual(item["locator"], {"label": "lines 1-1", "line_start": 1, "line_end": 1})
        self.assertEqual(item["egress"]["restriction"], "approved_remote")
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(response))
        self.assertLessEqual(response["context"]["token_usage"]["context_bytes"], 1600)

    def test_model_cannot_override_identity_collection_scope_destination_or_path(self):
        generation = self.store._generation()
        for key in ("principal", "collection", "collections", "access_scope_ref", "scope_ref", "destination", "db", "path", "root", "source_ids", "authority"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.handler.call("kre_retrieve", {"query": "quartz", key: "PRIVATE_PATH_SENTINEL"})
        self.assertEqual(generation, self.store._generation())
        self.assertEqual(self.store.principal, "operator-owned-domain")

    def test_remote_rejects_local_only_and_private_required_evidence(self):
        result = self.handler.call("kre_retrieve", {"query": "cobalt"})
        self.assertEqual(result["error"]["code"], "DESTINATION_DENIED")
        self.assertNotIn("LOCAL_SENTINEL", json.dumps(result))
        for source in ("local", "private"):
            result = self.handler.call("kre_retrieve", {"query": "quartz", "required_refs": [evidence_ref(self.item(source))]})
            self.assertEqual(result["error"]["code"], "REQUIRED_EVIDENCE_MISSING")
            self.assertEqual(result["context"]["context_text"], "")
            self.assertEqual(result["context"]["items"], [])
            self.assertNotIn("SENTINEL", json.dumps(result))

    def test_local_and_task_tools_require_explicit_boolean_host_attestation(self):
        for changes in ({"destination": "local_only"},
                        {"destination": "approved_remote", "task_tools": True, "local_client": True},
                        {"destination": "local_only", "local_client": "false"},
                        {"destination": "local_only", "local_client": True, "task_tools": 1}):
            with self.assertRaises(ValueError):
                KnowledgeTools(self.store, scope_ref="pilot", **changes)
        local = KnowledgeTools(self.store, scope_ref="pilot", destination="local_only", local_client=True)
        self.assertEqual({item["name"] for item in local.definitions()}, {"kre_retrieve", "kre_validate"})
        with self.assertRaises(ValueError):
            local.call("kre_checkpoint", {"task_id": "blocked", "card": {}})
        with self.assertRaises(ValueError):
            self.handler.call("kre_resume", {"task_id": "blocked"})

    def test_model_budget_can_only_narrow_and_required_passage_cannot_silently_drop(self):
        for query in ("", "x" * 4097, ["quartz"], json.loads('"\\ud800"')):
            with self.assertRaises(ValueError):
                self.handler.call("kre_retrieve", {"query": query})
        for fields in ({"max_bytes": 1601}, {"max_bytes": True}, {"max_bytes": 0},
                       {"max_items": 9}, {"max_items": False}, {"historical": 1}, {"fresh_only": "yes"}):
            with self.assertRaises(ValueError):
                self.handler.call("kre_retrieve", {"query": "quartz", **fields})
        result = self.handler.call("kre_retrieve", {"query": "quartz", "max_bytes": 80,
                                                   "required_refs": [evidence_ref(self.item("public"))]})
        self.assertEqual(result["error"]["code"], "BUDGET_TOO_SMALL")
        self.assertEqual(result["required"]["delivered"], [])
        self.assertEqual(result["context"]["context_text"], "")

    def test_revalidation_detects_tampering_and_later_policy_change(self):
        context = self.handler.call("kre_retrieve", {"query": "quartz"})["context"]
        self.assertEqual(self.handler.call("kre_validate", {"context": context})["validation"], "current")
        tampered = copy.deepcopy(context)
        tampered["context_text"] += " injected assertion"
        self.assertEqual(self.handler.call("kre_validate", {"context": tampered})["validation"], "denied")
        self.store.update_policy("public", freshness="stale")
        self.assertEqual(self.handler.call("kre_validate", {"context": context})["validation"], "changed")

    def test_local_checkpoint_resume_excludes_revoked_dependent_prose(self):
        local = KnowledgeTools(self.store, scope_ref="pilot", destination="local_only", local_client=True, task_tools=True)
        self.assertFalse(next(tool for tool in local.definitions() if tool["name"] == "kre_checkpoint")["annotations"]["readOnlyHint"])
        item = self.item("public")
        card = {"objective": {"text": "Synthetic review", "origin": "user_assertion", "refs": []},
                "constraints": [], "questions": [], "next_actions": [],
                "decisions": [{"text": item["text"], "origin": "source_evidence", "refs": [evidence_ref(item)]}]}
        local.call("kre_checkpoint", {"task_id": "review", "card": card})
        self.assertEqual(local.call("kre_resume", {"task_id": "review"})["card"], card)
        self.store.revoke("public")
        resumed = local.call("kre_resume", {"task_id": "review"})
        self.assertEqual(resumed["status"], "partial")
        self.assertEqual(resumed["card"]["decisions"], [])
        self.assertEqual(resumed["evidence"], [])
        self.assertNotIn(item["text"], json.dumps(resumed))


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.definitions = [_stdio.tool("synthetic", "Fixture only", {})]

    def test_initialization_notifications_and_serial_newline_framing(self):
        calls = []
        messages = [rpc(0, "tools/list"), initialization(),
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "synthetic"}},
                    rpc(2, "tools/list"), rpc(3, "tools/call", {"name": "synthetic", "arguments": {}}),
                    rpc(4, "ping"), initialization(5), rpc(6, "resources/list")]
        code, responses, _ = transport(wire(messages), self.definitions, lambda name, args: calls.append((name, args)) or {"value": 7})
        self.assertEqual(code, 0)
        self.assertEqual([response["id"] for response in responses], [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(responses[0]["error"]["code"], -32002)
        self.assertEqual(responses[1]["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(calls, [("synthetic", {})])
        self.assertEqual(json.loads(responses[3]["result"]["content"][0]["text"]), {"value": 7})
        self.assertNotIn("structuredContent", responses[3]["result"])
        self.assertEqual(responses[5]["error"]["code"], -32602)
        self.assertEqual(responses[6]["error"]["code"], -32601)

    def test_invalid_json_and_malformed_tool_names_recover_without_dispatch(self):
        calls = []
        invalid = b'{not-json}\n{"x":1,"x":2}\n{"x":NaN}\n\xff\n'
        messages = [initialization(), rpc(2, "tools/call", {"name": []}),
                    rpc(3, "tools/call", {"name": {}}), rpc(4, "tools/call", {"name": "synthetic", "arguments": []}), rpc(5, "ping")]
        code, responses, _ = transport(invalid + wire(messages), self.definitions, lambda *args: calls.append(args))
        self.assertEqual(code, 0)
        self.assertEqual([r["error"]["code"] for r in responses[:4]], [-32700] * 4)
        self.assertEqual([r["error"]["code"] for r in responses[5:8]], [-32602] * 3)
        self.assertEqual(responses[-1]["result"], {})
        self.assertEqual(calls, [])

    def test_tool_exception_does_not_reflect_arguments_or_internal_details(self):
        def fail(*args):
            raise PermissionError("PRIVATE_INTERNAL_PATH_OR_PROVIDER_DETAIL")
        code, responses, raw = transport(wire([initialization(), rpc(2, "tools/call", {"name": "synthetic", "arguments": {"secret": "PRIVATE_ARGUMENT"}})]), self.definitions, fail)
        self.assertEqual(code, 0)
        self.assertTrue(responses[-1]["result"]["isError"])
        self.assertEqual(json.loads(responses[-1]["result"]["content"][0]["text"]), {"error": "operation_denied_or_invalid"})
        self.assertNotIn(b"PRIVATE_", raw)

    def test_oversized_output_becomes_bounded_error_without_partial_payload(self):
        with patch.object(_stdio, "MAX_OUTPUT", 1024):
            code, responses, raw = transport(wire([initialization(), rpc(2, "tools/call", {"name": "synthetic"})]),
                                              self.definitions, lambda *args: {"text": "PRIVATE_OUTPUT" * 200})
        self.assertEqual(code, 0)
        self.assertEqual(responses[-1]["error"]["message"], "response_bound_exceeded")
        self.assertNotIn(b"PRIVATE_OUTPUT", raw)
        self.assertTrue(all(len(line) < 1024 for line in raw.splitlines()))

    def test_oversized_input_stops_without_dispatch_or_raw_echo(self):
        calls = []
        raw = b"PRIVATE_INPUT" * (_stdio.MAX_INPUT // 13 + 2) + b"\n" + wire([initialization()])
        code, responses, output = transport(raw, self.definitions, lambda *args: calls.append(args))
        self.assertEqual(code, 2)
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["error"]["message"], "request_bound_exceeded")
        self.assertNotIn(b"PRIVATE_INPUT", output)
        self.assertEqual(calls, [])


class LaunchTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "owned.sqlite3"
        with Store(str(self.path), principal="operator", scopes={"read": {"shared"}}) as store:
            store.ingest_text("public", "Synthetic quartz port 8042.", collection="shared", egress="approved_remote")

    def test_real_module_launch_uses_existing_owned_database_and_stdout_only_protocol(self):
        args = [sys.executable, "-m", "kre.mcp", "--db", str(self.path), "--principal", "fixed-pilot",
                "--collection", "shared", "--destination", "approved_remote"]
        messages = [initialization(), {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    rpc(2, "tools/list"), rpc(3, "tools/call", {"name": "kre_retrieve", "arguments": {"query": "quartz"}})]
        completed = subprocess.run(args, input=wire(messages), capture_output=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(completed.stderr, b"")
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([result["id"] for result in responses], [1, 2, 3])
        self.assertEqual({tool["name"] for tool in responses[1]["result"]["tools"]}, {"kre_retrieve", "kre_validate"})
        context = json.loads(responses[2]["result"]["content"][0]["text"])["context"]
        self.assertEqual(context["items"][0]["text"], "Synthetic quartz port 8042.")
        self.assertNotIn(str(self.path), completed.stdout.decode())

    def test_bad_operator_binding_or_sqlite_open_failure_has_private_generic_error(self):
        stderr = io.StringIO()
        args = ["--db", str(self.path), "--principal", "fixed", "--collection", "shared", "--destination", "local_only"]
        with redirect_stderr(stderr):
            self.assertEqual(main(args), 2)
        self.assertEqual(stderr.getvalue(), "kre: invalid or unavailable operator binding\n")
        stderr = io.StringIO()
        with patch("kre.mcp.Store", side_effect=sqlite3.OperationalError("PRIVATE_DATABASE_PATH")), redirect_stderr(stderr):
            self.assertEqual(main(args), 2)
        self.assertNotIn("PRIVATE_DATABASE_PATH", stderr.getvalue())
        self.assertNotIn(str(self.path), stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
