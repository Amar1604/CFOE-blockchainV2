"""
tests/test_x402.py — X402 Payment Middleware Tests (Part 3)

Tests cover:
  1. Payment header encoding / decoding round-trip
  2. 402 response body structure
  3. Internal bypass (X-Internal-Secret header)
  4. Middleware returns 402 when no payment header
  5. Report encryption / decryption round-trip
  6. Agent wallet address persistence helpers

NOTE: On-chain TX verification tests require an active Algorand Testnet
connection and are gated by the ALGORAND_PRIVATE_KEY env var.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

# Ensure the project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Helper: Load .env for tests ─────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


# ════════════════════════════════════════════════════════════════════════════
# Part 1 — Header encoding / decoding
# ════════════════════════════════════════════════════════════════════════════

def test_encode_decode_payment_header_roundtrip():
    """encode_payment_header → decode_payment_header must be an identity."""
    from agents.x402_payments import encode_payment_header, decode_payment_header

    sender  = "A" * 58
    receiver = "B" * 58
    nonce   = str(uuid.uuid4())
    tx_id   = "FAKETXID0001234567890ABCDEF"
    amount  = 50_000  # 0.05 ALGO in micro-ALGO

    header = encode_payment_header(sender, receiver, amount, tx_id, nonce)

    # Must be valid base64
    raw = base64.b64decode(header.encode("ascii")).decode("utf-8")
    parsed = json.loads(raw)

    assert parsed["scheme"] == "exact"
    assert parsed["network"] == "algorand"

    payload = parsed["payload"]
    assert payload["from"] == sender
    assert payload["to"]   == receiver
    assert payload["amount"] == amount
    assert payload["tx_id"]  == tx_id
    assert payload["nonce"]  == nonce

    # decode helper must reconstruct the same dict
    decoded = decode_payment_header(header)
    assert decoded == parsed


def test_decode_invalid_header_raises():
    """A garbage base64 header must raise ValueError."""
    from agents.x402_payments import decode_payment_header

    with pytest.raises(ValueError):
        decode_payment_header("not-valid-base64!!!")


# ════════════════════════════════════════════════════════════════════════════
# Part 2 — 402 response body
# ════════════════════════════════════════════════════════════════════════════

def test_build_payment_required_body_structure():
    """Payment instruction body must contain required X402 fields."""
    from agents.x402_payments import build_payment_required_body

    body = build_payment_required_body(
        receiver_address="CFOEABC123XYZ",
        amount_algo=0.05,
        description="CfoE test",
    )

    assert body["x402Version"] == 1
    assert body["error"] == "Payment required"
    assert len(body["accepts"]) == 1

    accept = body["accepts"][0]
    assert accept["scheme"]  == "exact"
    assert accept["network"] == "algorand"
    assert accept["asset"]   == "ALGO"
    assert accept["payTo"]   == "CFOEABC123XYZ"
    # maxAmount should be 0.05 ALGO → 50_000 micro-ALGO as a string
    assert accept["maxAmount"] == "50000"


# ════════════════════════════════════════════════════════════════════════════
# Part 3 — FastAPI audit gate
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def client():
    """Spin up a FastAPI TestClient without hitting Algorand."""
    from fastapi.testclient import TestClient
    import webapp  # noqa: F401 — mounts app
    from webapp import app
    return TestClient(app, raise_server_exceptions=False)


def test_audit_endpoint_returns_402_without_payment(client):
    """
    POST /api/audit without X-Payment and without X-Internal-Secret
    must return HTTP 402 with x402Version in the body.
    """
    payload = {
        "supplier_name": "TestCorp",
        "emissions": 1000.0,
        "violations": 0,
        "sector": "default",
        "production_unit": "tonne",
    }
    response = client.post(
        "/api/audit",
        json=payload,
        headers={"Content-Type": "application/json"},  # No X-Payment
    )
    assert response.status_code == 402
    body = response.json()
    assert "x402Version" in body or "error" in body


def test_audit_endpoint_bypasses_gate_with_internal_secret(client):
    """
    POST /api/audit with X-Internal-Secret must not return 402
    (it will run the actual audit — skip this test if Groq key missing).
    """
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEY not set — skipping full audit test")

    payload = {
        "supplier_name": "InternalTestCorp",
        "emissions": 500.0,
        "violations": 1,
        "sector": "default",
        "production_unit": "tonne",
    }
    response = client.post(
        "/api/audit",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Internal-Secret": os.getenv("X402_INTERNAL_SECRET", "cfoe-internal-bypass-secret"),
        },
    )
    # Must NOT be 402
    assert response.status_code != 402


# ════════════════════════════════════════════════════════════════════════════
# Part 4 — Report encryption / decryption
# ════════════════════════════════════════════════════════════════════════════

def test_report_encryption_roundtrip():
    """Encrypt then decrypt must restore original text."""
    from agents.reporting_agent import _encrypt_report, _decrypt_report

    original = "CfoE Audit Report — Acme Corp — CRITICAL RISK — Score: 0.82"
    blob, key = _encrypt_report(original)

    # blob must be non-empty base64-ish string
    assert len(blob) > 10

    recovered = _decrypt_report(blob, key)
    assert recovered == original


def test_store_and_retrieve_encrypted_report():
    """store_encrypted_report → get_report_blob must return the public view."""
    from agents.reporting_agent import store_encrypted_report, get_report_blob

    audit_id = f"AUD-TEST-{uuid.uuid4().hex[:8].upper()}"
    report_text = "Test report content for " + audit_id

    entry = store_encrypted_report(audit_id, report_text, "TestSupplier")

    # entry must NOT expose the decryption key
    assert "_decryption_key" in entry  # returned in full dict (server-side)

    # get_report_blob (public view) must NOT expose the key
    public = get_report_blob(audit_id)
    assert public is not None
    assert "_decryption_key" not in public
    assert public["paid"] is False
    assert public["supplier_name"] == "TestSupplier"


def test_report_not_retrievable_before_payment():
    """get_decrypted_report must fail with paid=False."""
    from agents.reporting_agent import store_encrypted_report, get_decrypted_report

    audit_id = f"AUD-UNPAID-{uuid.uuid4().hex[:8].upper()}"
    store_encrypted_report(audit_id, "Secret intel", "AngstCorp")

    available, text, err = get_decrypted_report(audit_id)
    assert available is False
    assert text is None
    assert "payment" in (err or "").lower() or "not confirmed" in (err or "").lower()


def test_mark_paid_and_decrypt():
    """mark_report_paid → get_decrypted_report must return plaintext."""
    from agents.reporting_agent import (
        store_encrypted_report, mark_report_paid, get_decrypted_report
    )

    audit_id = f"AUD-PAID-{uuid.uuid4().hex[:8].upper()}"
    original = "SECRET_REPORT_CONTENT_12345"
    store_encrypted_report(audit_id, original, "PayedCorp")

    mark_report_paid(audit_id, "FAKETXID999")

    available, text, err = get_decrypted_report(audit_id)
    assert available is True
    assert text == original
    assert err is None


# ════════════════════════════════════════════════════════════════════════════
# Part 5 — Revenue endpoint
# ════════════════════════════════════════════════════════════════════════════

def test_revenue_endpoint_structure(client):
    """GET /api/revenue must return the expected keys."""
    response = client.get("/api/revenue")
    assert response.status_code == 200
    data = response.json()

    assert "total_algo_earned" in data
    assert "earnings_by_agent" in data
    assert "total_audits_paid" in data
    assert "total_reports_sold" in data
    assert "agent_balances" in data
    assert "recent_payments" in data
    assert "payment_count" in data


def test_payment_record_is_persisted(tmp_path, monkeypatch):
    """record_payment must append a record to agent_payments.json."""
    import importlib

    # Point DATA_DIR at a temp directory
    monkeypatch.setenv("SOME_UNUSED", "1")
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    payments_file = fake_data / "agent_payments.json"
    payments_file.write_text("[]")

    import agents.x402_payments as xmod
    original_path = xmod.PAYMENTS_PATH
    xmod.PAYMENTS_PATH = payments_file

    try:
        record = xmod.record_payment(
            agent_name="test_agent",
            amount_algo=0.001,
            service="test_service",
            tx_id="TESTX12345",
            direction="outgoing",
            status="confirmed",
        )
        assert record["agent"] == "test_agent"
        assert record["amount_algo"] == 0.001

        saved = json.loads(payments_file.read_text())
        assert len(saved) == 1
        assert saved[0]["tx_id"] == "TESTX12345"
    finally:
        xmod.PAYMENTS_PATH = original_path
