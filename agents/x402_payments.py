"""
X402 Payment Layer for CfoE Agentic Commerce
=============================================

X402 is the HTTP 402 "Payment Required" protocol for machine-to-machine
micropayments.  Because the official x402-python SDK is still maturing,
we implement the critical wire-format details by hand on top of algosdk,
following the spec at:
  https://docs.cdp.coinbase.com/x402/docs/x402-protocol

Payment header format (request):
  X-Payment: base64(json({
      "scheme": "exact",
      "network": "algorand",
      "payload": {
          "from":    "<sender_address>",
          "to":      "<receiver_address>",
          "amount":  <micro-ALGO int>,
          "tx_id":   "<confirmed Algorand TX ID>",
          "nonce":   "<uuid4>"
      }
  }))

Payment instructions header (402 response):
  X-Payment-Required: base64(json({
      "scheme": "exact",
      "network": "algorand",
      "x402Version": 1,
      "accepts": [{
          "scheme":   "exact",
          "network":  "algorand",
          "maxAmount": "<micro-ALGO>",
          "asset":    "ALGO",
          "payTo":    "<receiver_address>",
          "description": "..."
      }],
      "error": "Payment required"
  }))

Rules enforced here:
  • Payment header is base64-encoded JSON — the format is exact and unforgiving.
  • On-chain confirmation is verified via algod — never trust the header alone.
  • Every payment is logged to data/agent_payments.json.
  • The audit pipeline never blocks for more than 10 seconds on confirmation.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("x402_payments")

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PAYMENTS_PATH = DATA_DIR / "agent_payments.json"

_pay_lock = threading.Lock()

# ── Constants ──────────────────────────────────────────────────────────────
ALGO_DECIMALS = 1_000_000          # 1 ALGO = 1_000_000 micro-ALGO
CONFIRMATION_TIMEOUT_SEC = 10      # Never block audit pipeline longer than this
X402_VERSION = 1
NETWORK = "algorand"
SCHEME = "exact"

# Default data-provider address (MonitorAgent pays searches here).
# Override via DATA_PROVIDER_ADDRESS env var.
DEFAULT_DATA_PROVIDER_ADDRESS = os.getenv(
    "DATA_PROVIDER_ADDRESS",
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ",  # zero address placeholder
)


# ── Persistence ────────────────────────────────────────────────────────────

def _load_payments() -> list:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PAYMENTS_PATH.exists():
        PAYMENTS_PATH.write_text("[]", encoding="utf-8")
    with _pay_lock:
        try:
            raw = PAYMENTS_PATH.read_text(encoding="utf-8").strip() or "[]"
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


def _save_payment(record: Dict[str, Any]) -> None:
    payments = _load_payments()
    payments.insert(0, record)
    with _pay_lock:
        PAYMENTS_PATH.write_text(json.dumps(payments[:1000], indent=2), encoding="utf-8")


# ── Algod helpers ──────────────────────────────────────────────────────────

def _get_algod_client():
    from algosdk.v2client import algod  # type: ignore
    server = os.getenv("ALGOD_SERVER", "https://testnet-api.algonode.cloud")
    token = os.getenv("ALGOD_TOKEN", "")
    if token:
        return algod.AlgodClient(token, server)
    return algod.AlgodClient("", server, headers={"User-Agent": "CfoE-X402/1.0"})


def _algo(amount_algo: float) -> int:
    """Convert ALGO float to micro-ALGO int."""
    return int(round(amount_algo * ALGO_DECIMALS))


def _from_micro(micro: int) -> float:
    return micro / ALGO_DECIMALS


# ── Wire format helpers ────────────────────────────────────────────────────

def encode_payment_header(
    sender_address: str,
    receiver_address: str,
    amount_micro: int,
    tx_id: str,
    nonce: Optional[str] = None,
) -> str:
    """
    Encode a completed payment as an X402 X-Payment header value.

    Returns base64(json(payload)) as per the x402 spec.
    """
    payload = {
        "scheme": SCHEME,
        "network": NETWORK,
        "payload": {
            "from": sender_address,
            "to": receiver_address,
            "amount": amount_micro,
            "tx_id": tx_id,
            "nonce": nonce or str(uuid.uuid4()),
        },
    }
    raw_json = json.dumps(payload, separators=(",", ":"))
    return base64.b64encode(raw_json.encode("utf-8")).decode("ascii")


def decode_payment_header(header_value: str) -> Dict[str, Any]:
    """
    Decode the X-Payment header value.

    Returns the parsed dict, or raises ValueError on bad format.
    """
    try:
        raw = base64.b64decode(header_value.encode("ascii")).decode("utf-8")
        return json.loads(raw)
    except Exception as exc:
        raise ValueError(f"Malformed X-Payment header: {exc}") from exc


def build_payment_required_body(
    receiver_address: str,
    amount_algo: float,
    description: str = "CfoE Audit Payment",
) -> Dict[str, Any]:
    """Build the 402 response JSON body with payment instructions."""
    return {
        "x402Version": X402_VERSION,
        "accepts": [
            {
                "scheme": SCHEME,
                "network": NETWORK,
                "maxAmount": str(_algo(amount_algo)),
                "asset": "ALGO",
                "payTo": receiver_address,
                "description": description,
            }
        ],
        "error": "Payment required",
    }


def encode_payment_required_header(
    receiver_address: str,
    amount_algo: float,
    description: str = "CfoE Audit Payment",
) -> str:
    """Encode payment instructions as base64 JSON for the X-Payment-Required header."""
    body = build_payment_required_body(receiver_address, amount_algo, description)
    raw_json = json.dumps(body, separators=(",", ":"))
    return base64.b64encode(raw_json.encode("utf-8")).decode("ascii")


# ── On-chain payment sending ───────────────────────────────────────────────

def send_payment(
    sender_private_key: str,
    sender_address: str,
    receiver_address: str,
    amount_algo: float,
    note: str = "X402 payment",
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Send an Algorand payment and wait up to CONFIRMATION_TIMEOUT_SEC for
    confirmation.

    Returns:
        (success: bool, tx_id: Optional[str], error_msg: Optional[str])
    """
    from algosdk import transaction  # type: ignore

    try:
        algod_client = _get_algod_client()
        params = algod_client.suggested_params()
        amount_micro = _algo(amount_algo)

        txn = transaction.PaymentTxn(
            sender=sender_address,
            sp=params,
            receiver=receiver_address,
            amt=amount_micro,
            note=note.encode("utf-8")[:1000],
        )
        signed = txn.sign(sender_private_key)
        tx_id = algod_client.send_transaction(signed)
        logger.info("Sent %s ALGO from %s... to %s... | TX: %s",
                    amount_algo, sender_address[:12], receiver_address[:12], tx_id)

        # Wait for confirmation with timeout
        start = time.time()
        confirmed = False
        while time.time() - start < CONFIRMATION_TIMEOUT_SEC:
            try:
                transaction.wait_for_confirmation(algod_client, tx_id, 2)
                confirmed = True
                break
            except Exception:
                time.sleep(1)

        if not confirmed:
            logger.warning("TX %s not confirmed within %d s — pending state", tx_id, CONFIRMATION_TIMEOUT_SEC)

        return True, tx_id, None

    except Exception as exc:
        error_msg = str(exc)
        logger.error("send_payment failed: %s", error_msg)
        return False, None, error_msg


# ── On-chain payment verification ─────────────────────────────────────────

def verify_payment_on_chain(
    tx_id: str,
    expected_receiver: str,
    expected_amount_micro: int,
    max_wait_sec: int = CONFIRMATION_TIMEOUT_SEC,
) -> Tuple[bool, Optional[str]]:
    """
    Verify an Algorand payment transaction on-chain.

    NEVER trust the X-Payment header alone — always verify on-chain.

    Returns:
        (verified: bool, error_msg: Optional[str])
    """
    try:
        algod_client = _get_algod_client()
        start = time.time()

        while time.time() - start < max_wait_sec:
            try:
                info = algod_client.pending_transaction_info(tx_id)
                if info.get("confirmed-round") and info.get("confirmed-round") > 0:
                    # Transaction confirmed — check amounts
                    txn = info.get("txn", {}).get("txn", {})
                    receiver = txn.get("rcv", "")
                    amount = txn.get("amt", 0)

                    if receiver != expected_receiver:
                        return False, f"Wrong receiver: expected {expected_receiver}, got {receiver}"

                    if amount < expected_amount_micro:
                        return False, (
                            f"Insufficient amount: expected {expected_amount_micro} µALGO "
                            f"(={_from_micro(expected_amount_micro):.4f} ALGO), "
                            f"got {amount} µALGO"
                        )

                    logger.info("Payment TX %s verified on-chain ✓", tx_id)
                    return True, None

                time.sleep(1)

            except Exception:
                time.sleep(1)

        return False, f"Timeout: TX {tx_id} not confirmed within {max_wait_sec}s"

    except Exception as exc:
        return False, str(exc)


# ── High-level payment recording ──────────────────────────────────────────

def record_payment(
    agent_name: str,
    amount_algo: float,
    service: str,
    tx_id: Optional[str],
    direction: str = "outgoing",     # "outgoing" or "incoming"
    status: str = "confirmed",       # "confirmed", "pending", "failed"
    audit_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Append a payment record to data/agent_payments.json."""
    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent_name,
        "direction": direction,
        "amount_algo": amount_algo,
        "amount_micro": _algo(amount_algo),
        "service": service,
        "tx_id": tx_id,
        "status": status,
    }
    if audit_id:
        record["audit_id"] = audit_id
    _save_payment(record)
    logger.info(
        "[X402] %s | agent=%s | %.4f ALGO | %s | TX=%s",
        direction.upper(), agent_name, amount_algo, service, tx_id or "N/A",
    )
    return record


# ── MonitorAgent search payment ────────────────────────────────────────────

def pay_for_search(
    agent_name: str = "monitor_agent",
    amount_algo: float = 0.001,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    MonitorAgent sends 0.001 ALGO to the data provider before each Tavily search.

    Returns (success, tx_id, error_msg).
    Also checks balance and triggers top-up if needed.
    """
    from agents.agent_wallets import (  # type: ignore
        get_agent_address, get_agent_private_key, check_and_topup
    )

    sender_address = get_agent_address(agent_name)
    sender_pk = get_agent_private_key(agent_name)

    if not sender_address or not sender_pk:
        logger.warning("pay_for_search: no wallet for %s — skipping payment", agent_name)
        return False, None, "Agent wallet not configured"

    # Check balance — top-up if needed (non-blocking)
    try:
        from agents.agent_wallets import get_agent_balance, LOW_BALANCE_THRESHOLD  # type: ignore
        balance = get_agent_balance(agent_name)
        if balance < LOW_BALANCE_THRESHOLD:
            logger.warning(
                "MonitorAgent balance (%.6f ALGO) below threshold — requesting top-up", balance
            )
            check_and_topup(agent_name)
    except Exception as exc:
        logger.warning("Balance check failed: %s", exc)

    receiver_address = os.getenv("DATA_PROVIDER_ADDRESS", DEFAULT_DATA_PROVIDER_ADDRESS)

    success, tx_id, err = send_payment(
        sender_private_key=sender_pk,
        sender_address=sender_address,
        receiver_address=receiver_address,
        amount_algo=amount_algo,
        note=f"X402: CfoE MonitorAgent Tavily search payment",
    )

    status = "confirmed" if success else "failed"
    record_payment(
        agent_name=agent_name,
        amount_algo=amount_algo,
        service="tavily_search",
        tx_id=tx_id,
        direction="outgoing",
        status=status,
    )

    return success, tx_id, err


# ── Audit gate: validate incoming payment header ───────────────────────────

def validate_audit_payment(
    x_payment_header: str,
    auditor_address: str,
    required_amount_algo: float = 0.05,
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validate an X-Payment header for the POST /api/audit gate.

    Steps:
      1. Decode the base64 JSON header
      2. Check network / scheme / receiver
      3. Verify on-chain via algod (never trust header alone)

    Returns:
        (valid: bool, error_msg: Optional[str], payment_info: Optional[dict])
    """
    try:
        parsed = decode_payment_header(x_payment_header)
    except ValueError as exc:
        return False, str(exc), None

    payload = parsed.get("payload", {})
    tx_id = payload.get("tx_id")
    receiver = payload.get("to")
    amount_micro = payload.get("amount", 0)
    scheme = parsed.get("scheme")
    network = parsed.get("network")

    if scheme != SCHEME:
        return False, f"Unsupported payment scheme: {scheme}", None
    if network != NETWORK:
        return False, f"Unsupported network: {network}", None
    if not tx_id:
        return False, "Missing tx_id in payment payload", None
    if receiver != auditor_address:
        return False, f"Payment sent to wrong address: {receiver}", None

    # On-chain verification
    required_micro = _algo(required_amount_algo)
    verified, error = verify_payment_on_chain(
        tx_id=tx_id,
        expected_receiver=auditor_address,
        expected_amount_micro=required_micro,
    )

    if not verified:
        return False, f"On-chain verification failed: {error}", None

    payment_info = {
        "tx_id": tx_id,
        "from": payload.get("from"),
        "to": receiver,
        "amount_algo": _from_micro(amount_micro),
        "verified": True,
    }
    return True, None, payment_info


# ── Report sale helpers ────────────────────────────────────────────────────

def verify_report_payment(
    tx_id: str,
    reporting_agent_address: str,
    required_amount_algo: float = 0.02,
) -> Tuple[bool, Optional[str]]:
    """
    Verify a report-access payment on-chain for the ReportingAgent.

    Returns (verified: bool, error_msg: Optional[str]).
    """
    required_micro = _algo(required_amount_algo)
    verified, error = verify_payment_on_chain(
        tx_id=tx_id,
        expected_receiver=reporting_agent_address,
        expected_amount_micro=required_micro,
    )

    if verified:
        record_payment(
            agent_name="reporting_agent",
            amount_algo=required_amount_algo,
            service="report_access",
            tx_id=tx_id,
            direction="incoming",
            status="confirmed",
        )
    return verified, error
