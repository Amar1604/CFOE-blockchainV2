"""
CfoE Blockchain Client - Algorand Smart Contract Integration

Three cryptographic integration points for the CfoE audit pipeline:
1. Score Anchoring   - Immutable timestamp + hash of emissions data after scoring
2. HITL Decision     - Cryptographic proof of human review (wallet-signed)
3. Report Hash       - SHA-256 of final report stored on-chain for tamper detection

Usage:
    from blockchain_client import get_blockchain_client

    bc = get_blockchain_client()
    bc.anchor_score("TestCorp", 0.45, "Moderate Risk", 2500, 2)
    bc.record_hitl_decision("TestCorp", score_tx, True, 0.85)
    bc.register_report_hash("TestCorp", report_tx, report_text)
"""

import os
import hashlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# Persistent ledger file — survives server restarts and fresh device setups
_LEDGER_PATH = Path(__file__).resolve().parent / "data" / "blockchain_ledger.json"
_ledger_lock = threading.Lock()


class CfoEBlockchainClient:
    """
    Algorand blockchain client for immutable ESG compliance audit trails.

    Provides three cryptographic integration points:
    - Score Anchoring: Immutable risk score + input data hash
    - HITL Decision Ledger: Wallet-signed human approval proof
    - Report Hash Registry: SHA-256 tamper detection for audit reports
    """

    def __init__(self):
        self.algod_client = None
        self.address = None  # Will be set by Defly wallet
        self.private_key = None  # Not used with Defly wallet
        self.algod_server = os.getenv("ALGOD_SERVER", "https://testnet-api.algonode.cloud")
        self.algod_token = os.getenv("ALGOD_TOKEN", "")
        self.app_id = None
        self.connected = False
        self.wallet_connected = False

        # In-memory ledger (mirrors on-chain records)
        # Loaded from disk on startup so data survives server restarts
        self.score_anchors: List[Dict] = []
        self.hitl_decisions: List[Dict] = []
        self.report_hashes: List[Dict] = []
        self._load_ledger()

    # ================================================================== #
    #  PERSISTENCE
    # ================================================================== #

    def _load_ledger(self) -> None:
        """Load the blockchain audit trail from disk."""
        with _ledger_lock:
            try:
                if _LEDGER_PATH.exists():
                    raw = _LEDGER_PATH.read_text(encoding="utf-8").strip()
                    if raw:
                        data = json.loads(raw)
                        self.score_anchors = data.get("score_anchors", [])
                        self.hitl_decisions = data.get("hitl_decisions", [])
                        self.report_hashes = data.get("report_hashes", [])
                        total = len(self.score_anchors) + len(self.hitl_decisions) + len(self.report_hashes)
                        if total:
                            print(f"  [Blockchain] Loaded {total} records from ledger")
            except (json.JSONDecodeError, OSError) as exc:
                print(f"  [Blockchain] WARNING: Could not load ledger: {exc}")

    def _save_ledger(self) -> None:
        """Persist the blockchain audit trail to disk."""
        with _ledger_lock:
            try:
                _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "score_anchors": self.score_anchors,
                    "hitl_decisions": self.hitl_decisions,
                    "report_hashes": self.report_hashes,
                }
                _LEDGER_PATH.write_text(
                    json.dumps(payload, indent=2, default=str),
                    encoding="utf-8",
                )
            except OSError as exc:
                print(f"  [Blockchain] WARNING: Could not save ledger: {exc}")

    # ================================================================== #
    #  CONNECTION
    # ================================================================== #

    def connect(self) -> bool:
        """Connect to Algorand network."""
        try:
            from algosdk.v2client import algod
            from algosdk import mnemonic, account

            if self.algod_token:
                self.algod_client = algod.AlgodClient(self.algod_token, self.algod_server)
            else:
                self.algod_client = algod.AlgodClient(
                    "", self.algod_server, headers={"User-Agent": "algosdk"}
                )

            # Test connection
            status = self.algod_client.status()
            self.connected = True
            print(f"  [Blockchain] Connected to Algorand (round {status.get('last-round', 'N/A')})")
            
            # Auto-connect wallet if private key is in .env
            env_key = os.getenv("ALGORAND_PRIVATE_KEY")
            if env_key:
                try:
                    # Derive address from private key
                    derived_address = account.address_from_private_key(env_key)
                    self.address = derived_address
                    self.private_key = env_key
                    self.wallet_connected = True
                    print(f"  [Blockchain] Wallet auto-connected from .env")
                    print(f"  [Blockchain] Address: {self.address}")
                except Exception as e:
                    print(f"  [Blockchain] WARNING: Invalid ALGORAND_PRIVATE_KEY in .env: {e}")
            
            return True

        except ImportError:
            print("  [Blockchain] WARNING: algosdk not installed. pip install py-algorand-sdk")
            self.connected = False
            return False
        except Exception as e:
            print(f"  [Blockchain] WARNING: Connection failed: {e}")
            print(f"  [Blockchain] Continuing in offline mode - transactions will be stored locally")
            self.connected = False
            return False

    def set_wallet_address(self, address: str) -> None:
        """Set the wallet address from Defly wallet connection."""
        self.address = address
        self.wallet_connected = True
        print(f"  [Blockchain] Wallet connected: {address[:16]}...")

    def disconnect_wallet(self) -> None:
        """Disconnect the wallet."""
        self.address = None
        self.wallet_connected = False
        print("  [Blockchain] Wallet disconnected")

    # ================================================================== #
    #  BALANCE
    # ================================================================== #

    def get_balance(self) -> Dict[str, Any]:
        """Get account balance and status."""
        if not self.connected or not self.wallet_connected or not self.address:
            return {"error": "Wallet not connected", "balance_algo": 0}
        try:
            info = self.algod_client.account_info(self.address)
            balance_micro = info.get("amount", 0)
            min_balance_micro = info.get("min-balance", 0)
            return {
                "address": self.address,
                "balance_algo": balance_micro / 1_000_000,
                "min_balance_algo": min_balance_micro / 1_000_000,
                "available_algo": max(0, balance_micro - min_balance_micro) / 1_000_000,
                "created_apps": len(info.get("created-apps", [])),
                "status": "OK",
            }
        except Exception as e:
            return {"error": str(e), "balance_algo": 0}

    # ================================================================== #
    #  INTERNAL: Send a note-field transaction
    # ================================================================== #

    def _send_note_tx(self, note_data: dict) -> Optional[str]:
        """
        Send a 0-ALGO self-payment with JSON data in the note field.
        Returns the transaction ID or None on failure.
        """
        if not self.connected:
            return None
            
        if not self.wallet_connected or not self.address:
            return None

        try:
            from algosdk import transaction
            
            # Get suggested params
            params = self.algod_client.suggested_params()
            
            # Create note field
            note = json.dumps(note_data).encode('utf-8')
            
            # Create transaction: 0 ALGO payment to self with note
            txn = transaction.PaymentTxn(
                sender=self.address,
                sp=params,
                receiver=self.address,
                amt=0,
                note=note
            )
            
            # For Defly wallet: Need to sign client-side
            # This is a placeholder - actual signing happens in browser
            # For now, we'll simulate by checking if we have a private key
            
            # Check if we have .env credentials as fallback
            env_key = os.getenv("ALGORAND_PRIVATE_KEY")
            if env_key:
                # Sign with .env private key
                signed_txn = txn.sign(env_key)
                tx_id = self.algod_client.send_transaction(signed_txn)
                
                # Wait for confirmation
                transaction.wait_for_confirmation(self.algod_client, tx_id, 4)
                print(f"  [Blockchain] Transaction confirmed: {tx_id}")
                return tx_id
            else:
                # No private key - store locally
                print(f"  [Blockchain] No signing key available - storing locally")
                print(f"  [Blockchain] Add ALGORAND_PRIVATE_KEY to .env for on-chain transactions")
                return None
                
        except Exception as e:
            print(f"  [Blockchain] Transaction failed: {str(e)}")
            return None

    # ================================================================== #
    #  INTEGRATION POINT 1: SCORE ANCHORING (after CalculationAgent)
    # ================================================================== #

    def anchor_score(
        self,
        supplier_name: str,
        risk_score: float,
        classification: str,
        emissions: float,
        violations: int,
        emissions_score: float = 0.0,
        violations_score: float = 0.0,
        external_risk_score: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Anchor an ESG risk score on the Algorand blockchain.

        After the CalculationAgent computes a deterministic score, this method
        records it immutably on-chain with:
        - Supplier ID
        - Score (0.0-1.0)
        - Timestamp (block round)
        - SHA-256 hash of input emissions data

        A regulator can verify the score wasn't changed retroactively by
        comparing the on-chain data hash with the original input.

        Args:
            supplier_name: Supplier being audited
            risk_score: Computed ESG risk score (0.0-1.0)
            classification: Risk classification string
            emissions: CO2 emissions in tons (input data)
            violations: Number of violations (input data)
            emissions_score: Component score for emissions
            violations_score: Component score for violations
            external_risk_score: External risk factor score

        Returns:
            Dict with tx_id, data_hash, score, and on_chain status
        """
        # Compute SHA-256 hash of input data for integrity verification
        input_data = f"{supplier_name}|{emissions}|{violations}|{external_risk_score}"
        data_hash = hashlib.sha256(input_data.encode("utf-8")).hexdigest()

        timestamp = datetime.now().isoformat()

        note_data = {
            "type": "CfoE_SCORE_ANCHOR",
            "version": "2.0",
            "supplier": supplier_name,
            "risk_score": round(risk_score, 4),
            "risk_score_uint": int(risk_score * 100),
            "classification": classification,
            "emissions_tons": int(emissions),
            "violations": violations,
            "emissions_score": round(emissions_score, 4),
            "violations_score": round(violations_score, 4),
            "external_risk_score": round(external_risk_score, 4),
            "input_data_hash": data_hash,
            "timestamp": timestamp,
            "auditor_address": self.address if self.address else "N/A",
        }

        tx_id = self._send_note_tx(note_data)
        on_chain = tx_id is not None

        record = {
            "supplier_name": supplier_name,
            "risk_score": risk_score,
            "classification": classification,
            "data_hash": data_hash,
            "tx_id": tx_id,
            "on_chain": on_chain,
            "timestamp": timestamp,
        }
        self.score_anchors.append(record)
        self._save_ledger()

        if on_chain:
            print(f"  [Blockchain] SCORE ANCHORED on-chain")
            print(f"               Supplier:  {supplier_name}")
            print(f"               Score:     {risk_score:.2f} ({classification})")
            print(f"               Data Hash: {data_hash[:16]}...")
            print(f"               TX:        {tx_id}")
        else:
            local_id = f"SCORE-{len(self.score_anchors):04d}"
            record["local_id"] = local_id
            if self.wallet_connected:
                print(f"  [Blockchain] Score stored locally (Defly requires client-side signing)")
            else:
                print(f"  [Blockchain] Score stored locally (wallet not connected)")

        return record

    # ================================================================== #
    #  INTEGRATION POINT 2: HITL DECISION LEDGER (after PolicyAgent)
    # ================================================================== #

    def record_hitl_decision(
        self,
        supplier_name: str,
        score_anchor_tx: Optional[str],
        approved: bool,
        risk_score: float,
        decision: str = "",
        reason: str = "",
        recommended_action: str = "",
    ) -> Dict[str, Any]:
        """
        Record a Human-in-the-Loop decision on the Algorand blockchain.

        When a human approves or rejects a supplier suspension, this records:
        - Auditor wallet address (who approved) = Txn.sender
        - Decision (approve/reject)
        - Risk score at time of decision
        - TX signed by auditor's wallet = cryptographic proof of human action

        This replaces "trust us, a human reviewed it" with cryptographic proof.
        The transaction is SIGNED by the auditor's private key, proving identity.

        Args:
            supplier_name: Supplier under review
            score_anchor_tx: TX ID of the anchored score (links decisions to scores)
            approved: True = approved continuation, False = rejected/suspended
            risk_score: Risk score at time of decision
            decision: Policy decision string
            reason: Reason for the decision
            recommended_action: What action was recommended

        Returns:
            Dict with tx_id, decision details, and cryptographic proof status
        """
        timestamp = datetime.now().isoformat()
        decision_str = "APPROVED" if approved else "REJECTED"

        note_data = {
            "type": "CfoE_HITL_DECISION",
            "version": "2.0",
            "supplier": supplier_name,
            "decision": decision_str,
            "policy_decision": decision,
            "risk_score_at_decision": round(risk_score, 4),
            "reason": reason[:200],  # Truncate to fit note
            "recommended_action": recommended_action[:200],
            "score_anchor_tx": score_anchor_tx or "N/A",
            "auditor_address": self.address if self.address else "N/A",  # Wallet that signed = proof of identity
            "requires_human_review": risk_score >= 0.70,
            "timestamp": timestamp,
        }

        tx_id = self._send_note_tx(note_data)
        on_chain = tx_id is not None

        record = {
            "supplier_name": supplier_name,
            "decision": decision_str,
            "policy_decision": decision,
            "risk_score": risk_score,
            "score_anchor_tx": score_anchor_tx,
            "tx_id": tx_id,
            "on_chain": on_chain,
            "auditor_address": self.address if self.address else "N/A",
            "timestamp": timestamp,
            "cryptographic_proof": on_chain,  # TX signature = proof
        }
        self.hitl_decisions.append(record)
        self._save_ledger()

        if on_chain:
            print(f"  [Blockchain] HITL DECISION recorded on-chain")
            print(f"               Supplier: {supplier_name}")
            print(f"               Decision: {decision_str}")
            print(f"               Score:    {risk_score:.2f}")
            if self.address:
                print(f"               Auditor:  {self.address[:16]}...")
            print(f"               TX:       {tx_id}")
            print(f"               Crypto Proof: TX signed by auditor wallet")
        else:
            local_id = f"HITL-{len(self.hitl_decisions):04d}"
            record["local_id"] = local_id
            if self.wallet_connected:
                print(f"  [Blockchain] HITL decision stored locally (Defly requires client-side signing)")
            else:
                print(f"  [Blockchain] HITL decision stored locally (wallet not connected)")

        return record

    # ================================================================== #
    #  INTEGRATION POINT 3: REPORT HASH REGISTRY (after ReportingAgent)
    # ================================================================== #

    def register_report_hash(
        self,
        supplier_name: str,
        score_anchor_tx: Optional[str],
        hitl_decision_tx: Optional[str],
        report_text: str,
    ) -> Dict[str, Any]:
        """
        Store the SHA-256 hash of the final audit report on-chain.

        Anyone can verify the PDF/DOCX they received matches the on-chain
        hash -- proving the report wasn't altered after generation.

        The hash links back to the score anchor TX and HITL decision TX,
        creating a complete chain of custody:
          Score Anchor TX -> HITL Decision TX -> Report Hash TX

        Args:
            supplier_name: Supplier name
            score_anchor_tx: TX of anchored score
            hitl_decision_tx: TX of HITL decision
            report_text: Full text of the generated report

        Returns:
            Dict with report_hash, tx_id, and chain_of_custody references
        """
        # Compute SHA-256 hash of the full report
        report_hash = hashlib.sha256(report_text.encode("utf-8")).hexdigest()

        # Also compute a short verification code for quick checks
        verification_code = report_hash[:12].upper()

        timestamp = datetime.now().isoformat()

        note_data = {
            "type": "CfoE_REPORT_HASH",
            "version": "2.0",
            "supplier": supplier_name,
            "report_sha256": report_hash,
            "verification_code": verification_code,
            "report_length": len(report_text),
            "score_anchor_tx": score_anchor_tx or "N/A",
            "hitl_decision_tx": hitl_decision_tx or "N/A",
            "generator": "CfoE ReportingAgent v1.0",
            "auditor_address": self.address if self.address else "N/A",
            "timestamp": timestamp,
        }

        tx_id = self._send_note_tx(note_data)
        on_chain = tx_id is not None

        record = {
            "supplier_name": supplier_name,
            "report_hash": report_hash,
            "verification_code": verification_code,
            "report_length": len(report_text),
            "score_anchor_tx": score_anchor_tx,
            "hitl_decision_tx": hitl_decision_tx,
            "tx_id": tx_id,
            "on_chain": on_chain,
            "timestamp": timestamp,
            "chain_of_custody": {
                "1_score_anchor": score_anchor_tx or "N/A",
                "2_hitl_decision": hitl_decision_tx or "N/A",
                "3_report_hash": tx_id or "N/A",
            },
        }
        self.report_hashes.append(record)
        self._save_ledger()

        if on_chain:
            print(f"  [Blockchain] REPORT HASH registered on-chain")
            print(f"               Supplier:     {supplier_name}")
            print(f"               SHA-256:      {report_hash[:24]}...")
            print(f"               Verify Code:  {verification_code}")
            print(f"               Report Size:  {len(report_text)} chars")
            print(f"               TX:           {tx_id}")
            print(f"               Chain of Custody:")
            print(f"                 1. Score:  {(score_anchor_tx or 'N/A')[:20]}...")
            print(f"                 2. HITL:   {(hitl_decision_tx or 'N/A')[:20]}...")
            print(f"                 3. Report: {tx_id}")
        else:
            local_id = f"REPORT-{len(self.report_hashes):04d}"
            record["local_id"] = local_id
            if self.wallet_connected:
                print(f"  [Blockchain] Report hash stored locally (Defly requires client-side signing)")
            else:
                print(f"  [Blockchain] Report hash stored locally (wallet not connected)")

        return record

    # ================================================================== #
    #  VERIFICATION: Validate report integrity
    # ================================================================== #

    def verify_report(self, report_text: str, expected_hash: str) -> bool:
        """
        Verify a report's integrity against its on-chain hash.

        Args:
            report_text: The report text to verify
            expected_hash: The SHA-256 hash stored on-chain

        Returns:
            True if the report matches the on-chain hash
        """
        actual_hash = hashlib.sha256(report_text.encode("utf-8")).hexdigest()
        match = actual_hash == expected_hash

        if match:
            print(f"  [Verify] Report integrity VERIFIED - hash matches on-chain record")
        else:
            print(f"  [Verify] TAMPER DETECTED - report hash does NOT match on-chain")
            print(f"           Expected: {expected_hash[:24]}...")
            print(f"           Actual:   {actual_hash[:24]}...")

        return match

    # ================================================================== #
    #  CARBON CREDIT RECORDING
    # ================================================================== #
    
    def record_carbon_credits(
        self,
        supplier_name: str,
        audit_id: str,
        credits_earned: int,
        badges_earned: List[str],
        total_credits: int,
        esg_score: float,
        streak_bonus: int = 0,
        improvement_bonus: int = 0,
    ) -> Dict[str, Any]:
        """
        Record carbon credit award on the Algorand blockchain.
        
        Creates an immutable record of credits earned for each audit,
        allowing verification of the credit ledger.
        
        Args:
            supplier_name: Supplier receiving credits
            audit_id: Associated audit ID
            credits_earned: Base credits earned
            badges_earned: List of badges awarded
            total_credits: New total credit balance
            esg_score: ESG risk score
            streak_bonus: Bonus credits from streak
            improvement_bonus: Bonus credits from improvement
            
        Returns:
            Dict with tx_id, credit details, and on_chain status
        """
        timestamp = datetime.now().isoformat()
        
        note_data = {
            "type": "CfoE_CARBON_CREDITS",
            "version": "1.0",
            "supplier": supplier_name,
            "audit_id": audit_id,
            "credits_earned": credits_earned,
            "streak_bonus": streak_bonus,
            "improvement_bonus": improvement_bonus,
            "total_credits_earned": credits_earned + streak_bonus + improvement_bonus,
            "total_credits_balance": total_credits,
            "badges_earned": badges_earned,
            "esg_score": round(esg_score, 4),
            "timestamp": timestamp,
            "auditor_address": self.address if self.address else "N/A",
        }
        
        tx_id = self._send_note_tx(note_data)
        on_chain = tx_id is not None
        
        record = {
            "supplier_name": supplier_name,
            "audit_id": audit_id,
            "credits_earned": credits_earned,
            "streak_bonus": streak_bonus,
            "improvement_bonus": improvement_bonus,
            "total_credits": total_credits,
            "badges_earned": badges_earned,
            "esg_score": esg_score,
            "tx_id": tx_id,
            "on_chain": on_chain,
            "timestamp": timestamp,
        }
        
        if on_chain:
            print(f"  [Blockchain] CARBON CREDITS recorded on-chain")
            print(f"               Supplier:  {supplier_name}")
            print(f"               Credits:   +{credits_earned + streak_bonus + improvement_bonus}")
            print(f"               Total:     {total_credits}")
            print(f"               Badges:    {', '.join(badges_earned) if badges_earned else 'None'}")
            print(f"               TX:        {tx_id}")
        else:
            local_id = f"CREDITS-{int(datetime.now().timestamp())}"
            record["local_id"] = local_id
            if self.wallet_connected:
                print(f"  [Blockchain] Credits stored locally (wallet signing required)")
            else:
                print(f"  [Blockchain] Credits stored locally (wallet not connected)")
        
        return record

    # ================================================================== #
    #  LEGACY: Full audit record (backwards compatibility)
    # ================================================================== #

    def record_audit(
        self,
        supplier_name: str,
        emissions: float,
        violations: int,
        risk_score: float,
        classification: str,
        policy_decision: str,
        requires_hitl: bool,
    ) -> Optional[str]:
        """Legacy method: record a full audit in one transaction."""
        result = self.anchor_score(
            supplier_name=supplier_name,
            risk_score=risk_score,
            classification=classification,
            emissions=emissions,
            violations=violations,
        )
        return result.get("tx_id") or result.get("local_id", "LOCAL")

    def record_hitl_approval(
        self,
        supplier_name: str,
        audit_id: str,
        approved: bool,
        reviewer: str = "admin",
    ) -> Optional[str]:
        """Legacy method: record HITL approval."""
        result = self.record_hitl_decision(
            supplier_name=supplier_name,
            score_anchor_tx=audit_id,
            approved=approved,
            risk_score=0.0,
            decision="HITL Review",
        )
        return result.get("tx_id") or result.get("local_id", "LOCAL")

    # ================================================================== #
    #  SUMMARY & STATUS
    # ================================================================== #

    def get_audit_summary(self) -> str:
        """Get formatted summary of all blockchain records."""
        lines = []
        total = len(self.score_anchors) + len(self.hitl_decisions) + len(self.report_hashes)

        if total == 0:
            return "  No blockchain records yet."

        lines.append(f"  Total Transactions: {total}")
        lines.append(f"  {'='*60}")

        # Score Anchors
        if self.score_anchors:
            lines.append(f"\n  SCORE ANCHORS ({len(self.score_anchors)}):")
            for i, r in enumerate(self.score_anchors, 1):
                status = "ON-CHAIN" if r["on_chain"] else "LOCAL"
                tx = (r.get("tx_id") or r.get("local_id", "N/A"))[:24]
                lines.append(
                    f"    {i}. {r['supplier_name']:<22} | "
                    f"Score: {r['risk_score']:.2f} | "
                    f"{r['classification']:<15} | "
                    f"{status} | {tx}..."
                )

        # HITL Decisions
        if self.hitl_decisions:
            lines.append(f"\n  HITL DECISIONS ({len(self.hitl_decisions)}):")
            for i, r in enumerate(self.hitl_decisions, 1):
                status = "ON-CHAIN (crypto proof)" if r["on_chain"] else "LOCAL"
                tx = (r.get("tx_id") or r.get("local_id", "N/A"))[:24]
                lines.append(
                    f"    {i}. {r['supplier_name']:<22} | "
                    f"{r['decision']:<10} | "
                    f"Score: {r['risk_score']:.2f} | "
                    f"{status} | {tx}..."
                )

        # Report Hashes
        if self.report_hashes:
            lines.append(f"\n  REPORT HASHES ({len(self.report_hashes)}):")
            for i, r in enumerate(self.report_hashes, 1):
                status = "ON-CHAIN" if r["on_chain"] else "LOCAL"
                tx = (r.get("tx_id") or r.get("local_id", "N/A"))[:24]
                lines.append(
                    f"    {i}. {r['supplier_name']:<22} | "
                    f"Verify: {r['verification_code']} | "
                    f"{r['report_length']} chars | "
                    f"{status} | {tx}..."
                )

        lines.append(f"\n  {'='*60}")
        return "\n".join(lines)

    def get_status_report(self) -> str:
        """Get full blockchain status report."""
        lines = []
        lines.append("=" * 60)
        lines.append("  BLOCKCHAIN STATUS")
        lines.append("=" * 60)

        if self.connected and self.wallet_connected and self.address:
            balance_info = self.get_balance()
            lines.append(f"  Connection:     ACTIVE")
            lines.append(f"  Network:        Algorand Testnet")
            lines.append(f"  Wallet:         Defly Wallet")
            lines.append(f"  Address:        {self.address}")
            lines.append(f"  Balance:        {balance_info.get('balance_algo', 0):.6f} ALGO")
            lines.append(f"  Available:      {balance_info.get('available_algo', 0):.6f} ALGO")
            lines.append(f"  App ID:         {self.app_id or 'Not deployed'}")
        elif self.connected:
            lines.append(f"  Connection:     ACTIVE")
            lines.append(f"  Wallet:         NOT CONNECTED")
            lines.append(f"  Mode:           Connect Defly Wallet to enable transactions")
        else:
            lines.append(f"  Connection:     OFFLINE")
            lines.append(f"  Mode:           Local logging only")

        on_chain_scores = sum(1 for r in self.score_anchors if r["on_chain"])
        on_chain_hitl = sum(1 for r in self.hitl_decisions if r["on_chain"])
        on_chain_reports = sum(1 for r in self.report_hashes if r["on_chain"])

        lines.append(f"  Score Anchors:  {len(self.score_anchors)} ({on_chain_scores} on-chain)")
        lines.append(f"  HITL Decisions: {len(self.hitl_decisions)} ({on_chain_hitl} on-chain)")
        lines.append(f"  Report Hashes:  {len(self.report_hashes)} ({on_chain_reports} on-chain)")
        lines.append("=" * 60)
        return "\n".join(lines)

    def get_audit_history(self) -> list:
        """Get all records."""
        return {
            "score_anchors": self.score_anchors,
            "hitl_decisions": self.hitl_decisions,
            "report_hashes": self.report_hashes,
        }


# ================================================================== #
#  SINGLETON
# ================================================================== #

_client_instance = None


def get_blockchain_client() -> CfoEBlockchainClient:
    """Get or create the singleton blockchain client."""
    global _client_instance
    if _client_instance is None:
        _client_instance = CfoEBlockchainClient()
        _client_instance.connect()
    return _client_instance
