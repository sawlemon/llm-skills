"""Safety gates: dry-run blocking, bank restrictions, secret redaction."""

import unittest

from hindsight_bench.config import BenchConfig
from hindsight_bench.hindsight import HindsightClient
from hindsight_bench.safety import (
    PERSONAL_BANKS,
    SafetyError,
    SafetyGuard,
    redact,
    redact_obj,
)
from hindsight_bench.tracing import TraceRecorder
from tests.fakes import RecordingHindsightTransport


class SafetyGuardTests(unittest.TestCase):
    def test_network_gate(self):
        guard = SafetyGuard(allow_network=False, allow_persistence=False, dry_run=True)
        with self.assertRaises(SafetyError):
            guard.check_network("https://openrouter.ai/api/v1/chat/completions")

    def test_dry_run_blocks_all_writes(self):
        guard = SafetyGuard(allow_network=True, allow_persistence=True, dry_run=True, bank="bench_abc")
        with self.assertRaises(SafetyError):
            guard.check_hindsight_request("POST", "/v1/default/banks/bench_abc/memories")
        with self.assertRaises(SafetyError):
            guard.check_hindsight_request("DELETE", "/v1/default/banks/bench_abc/documents/doc1")
        # Reads are fine.
        guard.check_hindsight_request("POST", "/v1/default/banks/bench_abc/memories/recall")
        guard.check_hindsight_request("POST", "/v1/default/banks/bench_abc/memories/dry-run-extract")

    def test_persistence_gate_required_for_writes(self):
        guard = SafetyGuard(allow_network=True, allow_persistence=False, dry_run=False, bank="bench_abc")
        with self.assertRaises(SafetyError):
            guard.check_hindsight_request("POST", "/v1/default/banks/bench_abc/memories")

    def test_personal_banks_rejected_for_writes(self):
        guard = SafetyGuard(allow_network=True, allow_persistence=True, dry_run=False, bank="agents")
        with self.assertRaises(SafetyError):
            guard.check_write_bank()
        for bank in PERSONAL_BANKS:
            guard = SafetyGuard(True, True, False, bank=bank)
            with self.assertRaises(SafetyError, msg=bank):
                guard.check_write_bank()

    def test_only_bench_banks_writable(self):
        guard = SafetyGuard(True, True, False, bank="bench_run123")
        guard.check_write_bank()  # must not raise
        guard = SafetyGuard(True, True, False, bank="my-own-bank")
        with self.assertRaises(SafetyError):
            guard.check_write_bank()

    def test_dry_run_and_persistence_mutually_exclusive(self):
        guard = SafetyGuard(True, True, True, bank="bench_x")
        with self.assertRaises(SafetyError):
            guard.check_live_ready()


class RedactionTests(unittest.TestCase):
    def test_redact_keys_and_headers(self):
        text = "Authorization: Bearer sk-or-v1-abcdef123456 and api_key = 0123456789abcdef"
        cleaned = redact(text)
        self.assertNotIn("sk-or-v1-abcdef123456", cleaned)
        self.assertNotIn("0123456789abcdef", cleaned)
        self.assertIn("<REDACTED>", cleaned)

    def test_redact_obj_recursive(self):
        data = {"headers": {"Authorization": "Bearer tok123456789"}, "nested": ["sk-abcdef123456"]}
        cleaned = redact_obj(data)
        serialized = str(cleaned)
        self.assertNotIn("tok123456789", serialized)
        self.assertNotIn("sk-abcdef123456", serialized)


class HindsightClientGateTests(unittest.TestCase):
    def test_dry_run_blocks_retain_even_with_fake_transport(self):
        transport = RecordingHindsightTransport()
        config = BenchConfig(mode="live", allow_network=True, allow_persistence=True, dry_run=True,
                             hindsight_url="http://example.invalid", hindsight_bank="bench_x")
        client = HindsightClient(config.hindsight_url, config.guard, config.hindsight_bank, transport=transport)
        with self.assertRaises(SafetyError):
            client.retain("should not be stored")
        # Read-only calls still work, and nothing reached the write endpoint.
        client.recall("test query")
        client.dry_run_extract("read only")
        client.health()
        write_calls = [(m, p) for m, p in transport.calls if p.endswith("/memories")]
        self.assertEqual(write_calls, [])

    def test_persistence_enabled_allows_retain_to_bench_bank(self):
        transport = RecordingHindsightTransport()
        config = BenchConfig(mode="live", allow_network=True, allow_persistence=True, dry_run=False,
                             hindsight_url="http://example.invalid", hindsight_bank="bench_x")
        client = HindsightClient(config.hindsight_url, config.guard, config.hindsight_bank, transport=transport)
        client.retain("synthetic benchmark fact")
        self.assertIn(("POST", "default/banks/bench_x/memories"), transport.calls)

    def test_retain_to_personal_bank_blocked_before_transport(self):
        transport = RecordingHindsightTransport()
        config = BenchConfig(mode="live", allow_network=True, allow_persistence=True, dry_run=False,
                             hindsight_url="http://example.invalid", hindsight_bank="agents")
        client = HindsightClient(config.hindsight_url, config.guard, config.hindsight_bank, transport=transport)
        with self.assertRaises(SafetyError):
            client.retain("never stored")
        self.assertEqual(transport.calls, [])


class TraceRecorderTests(unittest.TestCase):
    def test_events_redacted_and_written(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            recorder = TraceRecorder(path, "run1")
            recorder.add("s", "c", "phase", token="sk-secret123456", latency_s=1.0)
            text = path.read_text()
            self.assertNotIn("sk-secret123456", text)
            self.assertIn("<REDACTED>", text)


if __name__ == "__main__":
    unittest.main()
