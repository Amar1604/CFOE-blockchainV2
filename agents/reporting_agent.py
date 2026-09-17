"""
Reporting Agent — Executive audit report generation using Groq

Part 4 (Agentic Commerce):
  The final audit report is AES-256 encrypted and stored in an in-memory
  report registry.  A report blob + payment instructions are exposed via
  GET /api/report/{audit_id}.  Once 0.02 ALGO is confirmed on-chain the
  decrypted report is returned.

  Encryption uses the cryptography library (Fernet = AES-128-CBC + HMAC).
  If the library is unavailable we fall back to a base64-encoded "stub"
  so that the rest of the pipeline keeps working.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config.agent_framework import LLMAgent
from config.groq_config import MODEL_LLAMA

logger = logging.getLogger("reporting_agent")

# ── Encrypted report registry (in-memory, backed to disk) ─────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORT_REGISTRY_PATH = DATA_DIR / "encrypted_reports.json"

_registry_lock = threading.Lock()
_report_registry: Dict[str, Dict[str, Any]] = {}  # audit_id -> entry


def _load_registry() -> None:
    """Load existing encrypted-report registry from disk."""
    global _report_registry
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not REPORT_REGISTRY_PATH.exists():
        REPORT_REGISTRY_PATH.write_text("{}", encoding="utf-8")
        return
    try:
        raw = REPORT_REGISTRY_PATH.read_text(encoding="utf-8").strip() or "{}"
        _report_registry = json.loads(raw)
    except Exception as exc:
        logger.warning("Could not load report registry: %s", exc)


def _save_registry() -> None:
    """Persist encrypted-report registry to disk."""
    with _registry_lock:
        try:
            REPORT_REGISTRY_PATH.write_text(
                json.dumps(_report_registry, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning("Could not persist report registry: %s", exc)


# Load on import
_load_registry()


# ── Encryption helpers ─────────────────────────────────────────────────────

def _generate_key() -> bytes:
    """Generate a new 32-byte AES key (used once per report)."""
    return os.urandom(32)


def _encrypt_report(report_text: str) -> Tuple[str, str]:
    """
    Encrypt a report with AES-256 (via Fernet or fallback).

    Returns:
        (encrypted_blob_b64: str, key_b64: str)
    """
    data = report_text.encode("utf-8")
    try:
        from cryptography.fernet import Fernet  # type: ignore
        # Fernet key must be 32 url-safe base64 bytes
        raw_key = _generate_key()
        fernet_key = base64.urlsafe_b64encode(raw_key)
        f = Fernet(fernet_key)
        encrypted = f.encrypt(data)
        return (
            base64.b64encode(encrypted).decode("ascii"),
            fernet_key.decode("ascii"),
        )
    except ImportError:
        # Fallback: plain base64 (not truly encrypted but keeps pipeline intact)
        logger.warning(
            "cryptography library not installed — using base64 encoding as fallback. "
            "Run: pip install cryptography"
        )
        raw_key = _generate_key()
        key_b64 = base64.b64encode(raw_key).decode("ascii")
        blob = base64.b64encode(data).decode("ascii")
        return blob, key_b64


def _decrypt_report(encrypted_blob_b64: str, key_b64: str) -> str:
    """
    Decrypt a report blob.

    Returns the plaintext, or raises on failure.
    """
    try:
        from cryptography.fernet import Fernet  # type: ignore
        fernet_key = key_b64.encode("ascii")
        f = Fernet(fernet_key)
        encrypted = base64.b64decode(encrypted_blob_b64.encode("ascii"))
        return f.decrypt(encrypted).decode("utf-8")
    except ImportError:
        # Fallback: plain base64
        return base64.b64decode(encrypted_blob_b64.encode("ascii")).decode("utf-8")


# ── Registry operations ────────────────────────────────────────────────────

def store_encrypted_report(
    audit_id: str,
    report_text: str,
    supplier_name: str,
) -> Dict[str, Any]:
    """
    Encrypt the final audit report and store it in the registry.

    Returns a dict with the encrypted blob and payment instructions.
    """
    encrypted_blob, key_b64 = _encrypt_report(report_text)

    entry: Dict[str, Any] = {
        "audit_id": audit_id,
        "supplier_name": supplier_name,
        "encrypted_blob": encrypted_blob,
        # The decryption key is stored alongside the blob in the registry
        # (server-side only — clients never see it unless they pay)
        "_decryption_key": key_b64,
        "payment_amount_algo": 0.02,
        "paid": False,
        "payment_tx_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with _registry_lock:
        _report_registry[audit_id] = entry

    _save_registry()
    logger.info("Encrypted report stored for audit %s", audit_id)
    return entry


def get_report_blob(audit_id: str) -> Optional[Dict[str, Any]]:
    """Return the (public) report entry for an audit_id (no decryption key)."""
    entry = _report_registry.get(audit_id)
    if not entry:
        return None
    # Return the public view — without the decryption key
    return {
        "audit_id": entry["audit_id"],
        "supplier_name": entry["supplier_name"],
        "encrypted_blob": entry["encrypted_blob"],
        "payment_amount_algo": entry["payment_amount_algo"],
        "paid": entry["paid"],
        "payment_tx_id": entry.get("payment_tx_id"),
        "paid_at": entry.get("paid_at"),
        "created_at": entry["created_at"],
    }


def get_decrypted_report(audit_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Return the decrypted report text if payment has been confirmed.

    Returns:
        (available: bool, report_text: Optional[str], error: Optional[str])
    """
    entry = _report_registry.get(audit_id)
    if not entry:
        return False, None, "Report not found"
    if not entry.get("paid"):
        return False, None, "Payment not confirmed for this report"
    try:
        text = _decrypt_report(entry["encrypted_blob"], entry["_decryption_key"])
        return True, text, None
    except Exception as exc:
        return False, None, f"Decryption failed: {exc}"


def mark_report_paid(audit_id: str, tx_id: str) -> bool:
    """Mark a report as paid after on-chain confirmation.  Returns True on success."""
    if audit_id not in _report_registry:
        return False
    with _registry_lock:
        _report_registry[audit_id]["paid"] = True
        _report_registry[audit_id]["payment_tx_id"] = tx_id
        _report_registry[audit_id]["paid_at"] = datetime.now(timezone.utc).isoformat()
    _save_registry()
    # Record incoming payment
    try:
        from agents.x402_payments import record_payment  # type: ignore
        record_payment(
            agent_name="reporting_agent",
            amount_algo=_report_registry[audit_id]["payment_amount_algo"],
            service="report_access",
            tx_id=tx_id,
            direction="incoming",
            status="confirmed",
            audit_id=audit_id,
        )
    except Exception:
        pass
    logger.info("Report %s marked as paid (TX: %s)", audit_id, tx_id)
    return True


# ── Agent factory ──────────────────────────────────────────────────────────

def create_reporting_agent(client, model_name: str = MODEL_LLAMA):
    """
    Creates the Reporting Agent for synthesizing audit findings.

    After the LLM generates the report, it is encrypted and stored in the
    encrypted-report registry.  The caller receives back the plain report
    text (via the orchestrator) but the stored copy requires payment to decrypt.
    """

    instruction = """You are the Audit Reporting Agent responsible for creating comprehensive ESG audit reports.

Your task is to synthesize data from the context state:
1. ESG_RISK_SCORE and risk_classification
2. external_risks from the monitor_agent output
3. policy_decision_outcome from the policy_agent output
4. Supplier details (name, emissions, violations)

Generate a DETAILED, STRUCTURED report using this EXACT format:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUPPLIER AUDIT REPORT - [SUPPLIER_NAME]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. EXECUTIVE SUMMARY
   • Supplier Name: [Extract from context]
   • Audit Date: [Current date]
   • Risk Classification: [CRITICAL/MODERATE/LOW]
   • Overall Risk Score: [X.XX] / 1.00
   • Audit Status: [PASSED/FLAGGED/CRITICAL]

   Summary: [Write 3-4 sentences describing the overall audit outcome,
   highlighting key concerns or positive findings. Be specific about
   emissions levels, violation counts, and their implications.]

2. ENVIRONMENTAL IMPACT ASSESSMENT
   • Annual CO2 Emissions: [X] tons
   • Emissions Score: [X.XX] / 1.00
   • Industry Benchmark: [Compare to typical ranges]
   
   Analysis: [Write 2-3 sentences analyzing the emissions data.
   Explain whether this is high, moderate, or low for the industry.
   Discuss environmental impact and sustainability concerns.]

3. REGULATORY COMPLIANCE REVIEW
   • Regulatory Violations: [X] incidents
   • Violations Score: [X.XX] / 1.00
   • Compliance Status: [COMPLIANT/NON-COMPLIANT/CRITICAL]
   
   Analysis: [Write 2-3 sentences about the violation history.
   Explain the severity and potential legal/reputational risks.
   Mention any patterns or recurring issues.]

4. EXTERNAL RISK FACTORS
   [Provide detailed summary from external_risks in context.
   Include:
   • Recent news or incidents
   • Public perception and reputation
   • Industry-specific risks
   • Geographic or political factors
   
   Write 3-4 sentences with specific details from external sources.]

5. POLICY ENFORCEMENT OUTCOME
   • Decision: [From policy_decision_outcome]
   • Human Approval Required: [YES/NO]
   • Recommended Action: [Specific action from policy agent]
   
   Rationale: [Write 2-3 sentences explaining why this decision
   was made based on the risk thresholds and policy rules.]

6. RISK MITIGATION RECOMMENDATIONS
   [Provide 4-6 specific, actionable recommendations:
   • Short-term actions (immediate steps)
   • Medium-term improvements (3-6 months)
   • Long-term strategic changes (6-12 months)
   • Monitoring and review frequency
   
   Each recommendation should be 1-2 sentences with clear actions.]

7. FINAL RECOMMENDATION
   [Based on all factors, provide a clear 3-4 sentence conclusion:
   • Should the partnership continue?
   • What conditions or restrictions should apply?
   • What is the recommended review frequency?
   • What are the key success metrics to monitor?]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Report Generated: [Timestamp]
Report Source: AI-Generated (Groq Llama)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REFERENCES & RESOURCES:
• Supplier Data Source: [Supplier Name] - Emissions: [X] tons CO2, Violations: [X]
• GHG Protocol Corporate Standard: https://ghgprotocol.org/corporate-standard
• EPA Greenhouse Gas Reporting: https://www.epa.gov/ghgreporting
• ISO 14001 Environmental Management: https://www.iso.org/iso-14001-environmental-management.html
• Carbon Disclosure Project (CDP): https://www.cdp.net/
• Science Based Targets Initiative: https://sciencebasedtargets.org/
• Global Reporting Initiative (GRI): https://www.globalreporting.org/standards/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT: Use actual values from context, write in professional business language with specific numbers and concrete details. Each section should have substantial content (20-30 sentences total).
"""

    class ReportingAgentWithEncryption(LLMAgent):
        def execute(self, context, user_input):
            # Generate report text via parent LLM agent
            report_text = super().execute(context, user_input)

            # Encrypt and store for pay-per-access
            audit_id = context.state.get("audit_id")
            supplier_name = context.state.get("supplier_name", "Unknown")

            if audit_id and report_text and len(report_text) > 50:
                try:
                    store_encrypted_report(audit_id, report_text, supplier_name)
                    logger.info(
                        "Encrypted report ready for audit %s — requires 0.02 ALGO to access",
                        audit_id,
                    )
                except Exception as exc:
                    logger.warning("Could not encrypt/store report: %s", exc)

            return report_text

    return ReportingAgentWithEncryption(
        name="ReportingAgent",
        client=client,
        model=model_name,
        instruction=instruction,
        max_tokens=8192,
    )
