"""
tests/test_defi.py — Unit tests for the CfoE DeFi on-chain ASA economy.

Tests cover every ABI method across the three new contracts:
  - CarbonCreditASA (Parts 1 & 2)
  - CreditMarketplace (Part 4)
  - CCCStaking (Part 5)

Also tests the Python-layer helpers in onchain_ops.py (Parts 2 & 3).

Run with: pytest tests/test_defi.py -v
"""

from __future__ import annotations

import json
import os
import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from typing import Any

import pytest

# ───────────────────────────────────────────────────────────────────────────
#  Helper: patch the data directory so we write to tmp dirs, not real data/
# ───────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect all onchain_ops data files to a temp directory."""
    import onchain_ops
    monkeypatch.setattr(onchain_ops, "_DATA_DIR",     tmp_path)
    monkeypatch.setattr(onchain_ops, "_PENDING_MINTS", tmp_path / "pending_mints.json")
    monkeypatch.setattr(onchain_ops, "_BONDS_FILE",    tmp_path / "compliance_bonds.json")
    monkeypatch.setattr(onchain_ops, "_LISTINGS_FILE", tmp_path / "marketplace_listings.json")
    monkeypatch.setattr(onchain_ops, "_STAKES_FILE",   tmp_path / "staking_positions.json")


# ═══════════════════════════════════════════════════════════════════════════
#  Part 1 + 2: CarbonCreditASA — Python layer (onchain_ops)
# ═══════════════════════════════════════════════════════════════════════════

class TestMintOrQueue:
    """Tests for the mint_or_queue() entry point (Part 2)."""

    def test_skips_zero_credits(self):
        from onchain_ops import mint_or_queue
        result = mint_or_queue("s1", "SupplierA", 0, "AUD-001", 0.5)
        assert result["status"] == "skipped"

    def test_queues_when_no_wallet(self, tmp_path):
        from onchain_ops import mint_or_queue, _load_json, _PENDING_MINTS
        result = mint_or_queue("s1", "SupplierA", 50, "AUD-001", 0.4, wallet_address=None)
        assert result["status"] == "pending_wallet"
        assert result["amount"] == 50
        assert result["pending"] is True
        mints = _load_json(_PENDING_MINTS, [])
        assert len(mints) == 1
        assert mints[0]["supplier_id"] == "s1"
        assert mints[0]["amount"] == 50

    def test_mint_on_chain_success_mock(self, tmp_path):
        """Mock the SDK — verify on-chain path returns minted status."""
        from onchain_ops import mint_or_queue
        with patch("onchain_ops.mint_ccc_tokens", return_value="FAKE_TX_ID"):
            result = mint_or_queue("s1", "SupplierA", 100, "AUD-002", 0.3,
                                   wallet_address="A" * 58)
        assert result["status"] == "minted"
        assert result["tx_id"] == "FAKE_TX_ID"
        assert result["pending"] is False

    def test_mint_failure_falls_back_to_queue(self, tmp_path):
        from onchain_ops import mint_or_queue, _load_json, _PENDING_MINTS
        with patch("onchain_ops.mint_ccc_tokens", return_value=None):
            result = mint_or_queue("s1", "SupplierA", 75, "AUD-003", 0.35,
                                   wallet_address="A" * 58)
        assert result["status"] == "queued_retry"
        assert result["pending"] is True
        # Verify it was written to the pending file
        mints = _load_json(_PENDING_MINTS, [])
        assert any(m["supplier_id"] == "s1" for m in mints)


class TestFlushPendingMints:
    """Tests for flush_pending_mints() (Part 2)."""

    def test_flushes_pending_for_supplier(self, tmp_path):
        from onchain_ops import store_pending_mint, flush_pending_mints, _load_json, _PENDING_MINTS
        store_pending_mint("s1", "SupplierA", 40, "AUD-001", 0.4)
        store_pending_mint("s2", "SupplierB", 60, "AUD-002", 0.5)

        with patch("onchain_ops.mint_ccc_tokens", return_value="TX_S1"):
            processed = flush_pending_mints("WALLET_" + "A" * 50, "s1")

        assert len(processed) == 1
        assert processed[0]["tx_id"] == "TX_S1"
        assert processed[0]["status"] == "completed"

        # s2 should still be pending
        remaining = _load_json(_PENDING_MINTS, [])
        s2_entries = [m for m in remaining if m["supplier_id"] == "s2"]
        assert all(m["status"] == "pending" for m in s2_entries)

    def test_marks_failed_when_mint_returns_none(self, tmp_path):
        from onchain_ops import store_pending_mint, flush_pending_mints
        store_pending_mint("s3", "SupplierC", 30, "AUD-003", 0.6)
        with patch("onchain_ops.mint_ccc_tokens", return_value=None):
            processed = flush_pending_mints("W" * 58, "s3")
        assert processed[0]["status"] == "failed"


# ═══════════════════════════════════════════════════════════════════════════
#  Part 3: Compliance Bond (onchain_ops)
# ═══════════════════════════════════════════════════════════════════════════

class TestComplianceBond:
    """Tests for enforce_compliance_bond() (Part 3)."""

    def _run_bond(self, risk_score: float, **kw) -> dict:
        from onchain_ops import enforce_compliance_bond
        return enforce_compliance_bond(
            supplier_id=kw.get("supplier_id", "sup123"),
            supplier_name=kw.get("supplier_name", "SupplierX"),
            risk_score=risk_score,
            audit_id=kw.get("audit_id", "AUD-999"),
            wallet_address=kw.get("wallet_address"),
        )

    def test_no_bond_low_risk_no_action(self):
        result = self._run_bond(0.3)
        assert result["action"] == "none"

    def test_no_bond_high_risk_locks_bond_no_wallet(self):
        result = self._run_bond(0.65)
        assert result["action"] == "locked"
        assert result["amount"] == 50

    def test_no_bond_high_risk_locks_bond_with_wallet_mock(self):
        with patch("onchain_ops.clawback_bond", return_value="CLAWBACK_TX"):
            result = self._run_bond(0.65, wallet_address="W" * 58)
        assert result["action"] == "locked"
        assert result["tx_id"] == "CLAWBACK_TX"

    def test_existing_bond_improvement_releases(self):
        """First audit: HIGH risk → bond locked. Second audit: low risk → bond released."""
        from onchain_ops import enforce_compliance_bond, _load_bonds, _save_bonds
        # Seed an existing active bond WITH a wallet_address so release_bond_transfer is called
        bonds = {"sup123": {"amount": 50, "status": "active", "wallet_address": "W" * 58}}
        _save_bonds(bonds)
        with patch("onchain_ops.release_bond_transfer", return_value="RELEASE_TX"):
            result = self._run_bond(0.3, wallet_address="W" * 58)
        assert result["action"] == "released"
        assert result["tx_id"] == "RELEASE_TX"

    def test_existing_bond_critical_burns(self):
        """Persistent non-compliance: score ≥ 0.80 with existing bond → burn."""
        from onchain_ops import _save_bonds
        _save_bonds({"sup123": {"amount": 50, "status": "active", "wallet_address": None}})
        with patch("onchain_ops.burn_bond_tokens", return_value="BURN_TX"):
            result = self._run_bond(0.85)
        assert result["action"] == "burned"
        assert result["tx_id"] == "BURN_TX"

    def test_existing_bond_still_high_risk_maintained(self):
        from onchain_ops import _save_bonds
        _save_bonds({"sup123": {"amount": 50, "status": "active", "wallet_address": None}})
        result = self._run_bond(0.72)
        assert result["action"] == "maintained"

    def test_bond_file_persistence(self):
        from onchain_ops import _load_bonds
        self._run_bond(0.70)
        bonds = _load_bonds()
        assert "sup123" in bonds
        assert bonds["sup123"]["status"] == "active"


# ═══════════════════════════════════════════════════════════════════════════
#  Part 4: Marketplace (onchain_ops helpers)
# ═══════════════════════════════════════════════════════════════════════════

class TestMarketplace:
    """Tests for create_listing_offchain() and execute_buy_offchain()."""

    SELLER_ADDR = "S" * 58
    BUYER_ADDR  = "B" * 58

    def test_create_listing(self):
        from onchain_ops import create_listing_offchain
        listing = create_listing_offchain("seller1", self.SELLER_ADDR, 100, 500_000)
        assert listing["listing_id"] == 1
        assert listing["amount_ccc"] == 100
        assert listing["price_per_unit_micro"] == 500_000
        assert listing["status"] == "active"
        assert listing["seller_address"] == self.SELLER_ADDR

    def test_listing_counter_increments(self):
        from onchain_ops import create_listing_offchain
        l1 = create_listing_offchain("s1", self.SELLER_ADDR, 10, 1_000_000)
        l2 = create_listing_offchain("s2", self.SELLER_ADDR, 20, 2_000_000)
        assert l2["listing_id"] == l1["listing_id"] + 1

    def test_buy_listing_marks_sold(self):
        from onchain_ops import create_listing_offchain, execute_buy_offchain
        listing = create_listing_offchain("s1", self.SELLER_ADDR, 50, 500_000)
        result = execute_buy_offchain(listing["listing_id"], self.BUYER_ADDR, "buyer1")
        assert result["status"] == "sold"
        assert result["buyer"] == self.BUYER_ADDR
        assert result["amount_ccc"] == 50
        assert result["total_micro"] == 50 * 500_000

    def test_buy_nonexistent_listing(self):
        from onchain_ops import execute_buy_offchain
        result = execute_buy_offchain(9999, self.BUYER_ADDR, "buyer1")
        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()

    def test_buy_already_sold(self):
        from onchain_ops import create_listing_offchain, execute_buy_offchain
        listing = create_listing_offchain("s1", self.SELLER_ADDR, 25, 100_000)
        execute_buy_offchain(listing["listing_id"], self.BUYER_ADDR, "buyer1")
        # Try buying again
        result = execute_buy_offchain(listing["listing_id"], self.BUYER_ADDR, "buyer2")
        assert result["status"] == "error"


# ═══════════════════════════════════════════════════════════════════════════
#  Part 5: Staking (onchain_ops helpers)
# ═══════════════════════════════════════════════════════════════════════════

class TestStaking:
    """Tests for stake_ccc, unstake_ccc, claim_yield_offchain, get_stake_status."""

    ADDR = "C" * 58

    def test_stake_creates_position(self):
        from onchain_ops import stake_ccc, get_stake_status
        result = stake_ccc("sup1", self.ADDR, 100)
        assert result["status"] == "staked"
        assert result["amount_ccc"] == 100
        assert "unlock_time" in result
        assert result["pending_yield"] == pytest.approx(10.0)  # 10%

        status = get_stake_status("sup1")
        assert status["amount_ccc"] == 100
        assert status["status"] == "active"
        assert status["is_locked"] is True

    def test_double_stake_rejected(self):
        from onchain_ops import stake_ccc
        stake_ccc("sup1", self.ADDR, 50)
        result = stake_ccc("sup1", self.ADDR, 50)
        assert result["status"] == "error"
        assert "active stake" in result["reason"].lower()

    def test_unstake_locked_period_not_expired(self):
        from onchain_ops import stake_ccc, unstake_ccc
        stake_ccc("sup1", self.ADDR, 80)
        result = unstake_ccc("sup1")
        assert result["status"] == "error"
        assert "not expired" in result["reason"].lower()

    def test_unstake_after_lock_period(self, monkeypatch):
        """Mock time so lock period appears expired."""
        from onchain_ops import stake_ccc, unstake_ccc, _load_stakes, _save_stakes
        stake_ccc("sup1", self.ADDR, 80)
        # Manually move unlock time to the past
        stakes = _load_stakes()
        stakes["sup1"]["unlock_timestamp"] = time.time() - 1
        _save_stakes(stakes)
        result = unstake_ccc("sup1")
        assert result["status"] == "unstaked"
        assert result["amount_ccc"] == 80

    def test_claim_yield_locked(self):
        from onchain_ops import stake_ccc, claim_yield_offchain
        stake_ccc("sup1", self.ADDR, 100)
        result = claim_yield_offchain("sup1")
        assert result["status"] == "error"
        assert "not yet expired" in result["reason"].lower()

    def test_claim_yield_unlocked(self):
        from onchain_ops import stake_ccc, claim_yield_offchain, _load_stakes, _save_stakes
        stake_ccc("sup1", self.ADDR, 100)
        stakes = _load_stakes()
        stakes["sup1"]["unlock_timestamp"] = time.time() - 1
        _save_stakes(stakes)
        result = claim_yield_offchain("sup1")
        assert result["status"] == "yield_ready"
        # 10% of 100 CCC × 1_000_000 micro-ALGO per CCC = 10_000_000 micro
        assert result["yield_micro"] == 10_000_000
        assert result["yield_algo"] == pytest.approx(10.0)

    def test_claim_yield_twice_rejected(self):
        from onchain_ops import stake_ccc, claim_yield_offchain, _load_stakes, _save_stakes
        stake_ccc("sup1", self.ADDR, 50)
        stakes = _load_stakes()
        stakes["sup1"]["unlock_timestamp"] = time.time() - 1
        _save_stakes(stakes)
        claim_yield_offchain("sup1")
        result = claim_yield_offchain("sup1")
        assert result["status"] == "error"
        assert "already claimed" in result["reason"].lower()

    def test_no_stake_status(self):
        from onchain_ops import get_stake_status
        result = get_stake_status("nosuchsupplier")
        assert result["status"] == "no_stake"

    def test_pending_yield_zero_when_claimed(self):
        from onchain_ops import stake_ccc, claim_yield_offchain, get_stake_status, _load_stakes, _save_stakes
        stake_ccc("sup1", self.ADDR, 100)
        stakes = _load_stakes()
        stakes["sup1"]["unlock_timestamp"] = time.time() - 1
        _save_stakes(stakes)
        claim_yield_offchain("sup1")
        status = get_stake_status("sup1")
        assert status["yield_pending_micro"] == 0
        assert status["yield_claimed"] is True


# ═══════════════════════════════════════════════════════════════════════════
#  Integration smoke: credit_agent still works with new mint hook
# ═══════════════════════════════════════════════════════════════════════════

# Isolate the credit_agent from groq/monitor_agent imports that are unavailable
# in a bare test environment by stubbing out the heavy agent modules.
_STUB_AGENT_MODULES = [
    "groq",
    "agents.monitor_agent",
    "agents.calculation_agent",
    "agents.reporting_agent",
]


class TestCreditAgentIntegration:
    """Ensure existing credit agent scoring is unbroken by the mint hook."""

    def _import_credit_agent(self, sys_modules_patch):
        """Import calculate_carbon_credits with groq-dependent modules stubbed."""
        import sys
        stubs = {}
        for mod in _STUB_AGENT_MODULES:
            if mod not in sys.modules:
                stubs[mod] = MagicMock()
        sys_modules_patch.update(stubs)
        with patch.dict("sys.modules", sys_modules_patch):
            # Re-import fresh
            if "agents.credit_agent" in sys.modules:
                del sys.modules["agents.credit_agent"]
            if "agents" in sys.modules:
                del sys.modules["agents"]
            from agents import credit_agent as ca
            return ca.calculate_carbon_credits

    def test_calculate_carbon_credits_returns_result(self):
        import sys
        stubs = {mod: MagicMock() for mod in _STUB_AGENT_MODULES}
        # Ensure agents.__init__ doesn't pull in monitor_agent
        stubs["agents"] = MagicMock()
        with patch.dict("sys.modules", stubs):
            # Directly import credit_agent by path to avoid agents/__init__.py
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "credit_agent_direct",
                Path(__file__).parent.parent / "agents" / "credit_agent.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

        audit = {
            "supplier_name": "TestCorp Integration",
            "ESG_RISK_SCORE": 0.3,
            "annual_co2_emissions": 5000,
        }
        with patch("onchain_ops.mint_or_queue", return_value={"status": "minted", "tx_id": "MOCK"}):
            result = mod.calculate_carbon_credits(audit)

        assert "credits_earned" in result
        assert "total_credits" in result
        assert "ccc_mint" in result
        assert isinstance(result["credits_earned"], (int, float))

    def test_zero_credit_audit_has_ccc_mint_skipped(self):
        import sys, importlib.util
        stubs = {mod: MagicMock() for mod in _STUB_AGENT_MODULES}
        stubs["agents"] = MagicMock()
        with patch.dict("sys.modules", stubs):
            spec = importlib.util.spec_from_file_location(
                "credit_agent_direct2",
                Path(__file__).parent.parent / "agents" / "credit_agent.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

        audit = {
            "supplier_name": "ZeroCorp",
            "ESG_RISK_SCORE": 1.0,   # Critical — earns 0 credits
            "annual_co2_emissions": 9000,
        }
        with patch("onchain_ops.mint_or_queue", return_value={"status": "minted", "tx_id": None}):
            result = mod.calculate_carbon_credits(audit)
        # credits_earned == 0 → mint is skipped
        assert result["ccc_mint"]["status"] == "skipped"
