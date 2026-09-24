"""
CfoE Carbon Credit ASA — Algorand Python (Puya) Smart Contract
Part 1: ASA Token Design

Token Spec:
  - Name:      CfoE Carbon Credit
  - Unit:      CCC
  - Decimals:  0  (whole credits only)
  - Supply:    Pure-minting model — starts at 0, manager mints on demand
  - Manager:   auditor wallet
  - Reserve:   auditor wallet
  - Clawback:  auditor wallet  (enables PolicyAgent to slash non-compliant suppliers)
  - Freeze:    auditor wallet

The contract itself does NOT create the ASA (ASA creation is done off-chain
via AlgoKit deploy_config.py); instead it manages the minting ledger and
exposes mint / clawback / burn ABI methods so the Python layer can call
them via ABI calls rather than raw key-field transactions.

Deployment: algokit compile python contract.py
            algokit deploy (via deploy_config.py)
"""

from algopy import (
    ARC4Contract,
    BoxMap,
    Global,
    GlobalState,
    Txn,
    UInt64,
    arc4,
    op,
    subroutine,
    itxn,
    Asset,
)
from algopy.arc4 import (
    String as ARC4String,
    UInt64 as ARC4UInt64,
    Bool as ARC4Bool,
    Address as ARC4Address,
    abimethod,
)


class CarbonCreditASA(ARC4Contract):
    """
    CfoE Carbon Credit ASA Manager Contract

    Manages issuance records, compliance bonds, and clawback authority
    for the CCC Algorand Standard Asset.  The actual ASA is created once
    via deploy_config and the asset_id is stored in global state.
    """

    def __init__(self) -> None:
        # ── Global state ──────────────────────────────────────────────
        self.admin = GlobalState(Global.creator_address)
        self.asset_id = GlobalState(UInt64(0))        # CCC ASA id (set after creation)
        self.total_minted = GlobalState(UInt64(0))     # cumulative tokens minted
        self.total_burned = GlobalState(UInt64(0))     # cumulative tokens burned (slashed)

        # ── Box storage: mint records ─────────────────────────────────
        # Key: supplier_address (32 bytes)   Value: total minted to that address
        self.mint_ledger = BoxMap(ARC4Address, ARC4UInt64, key_prefix=b"m_")

        # ── Box storage: compliance bonds ────────────────────────────
        # Key: supplier_address   Value: tokens currently bonded
        self.bond_ledger = BoxMap(ARC4Address, ARC4UInt64, key_prefix=b"b_")

    # ═══════════════════════════════════════════════════════════════════
    #  ADMIN METHODS
    # ═══════════════════════════════════════════════════════════════════

    @abimethod()
    def set_asset_id(self, asset_id: ARC4UInt64) -> None:
        """
        Register the CCC ASA id in contract global state.
        Called once after the ASA is created off-chain.
        Only callable by admin.
        """
        assert Txn.sender == self.admin, "Only admin can set asset id"
        assert self.asset_id.value == UInt64(0), "Asset id already set"
        self.asset_id.value = asset_id.native

    @abimethod()
    def update_admin(self, new_admin: ARC4Address) -> None:
        """Transfer admin rights to a new address."""
        assert Txn.sender == self.admin, "Only admin can transfer"
        self.admin.value = new_admin.native

    # ═══════════════════════════════════════════════════════════════════
    #  MINTING
    # ═══════════════════════════════════════════════════════════════════

    @abimethod()
    def record_mint(
        self,
        recipient: ARC4Address,
        amount: ARC4UInt64,
        audit_id: ARC4String,
    ) -> ARC4UInt64:
        """
        Record that `amount` CCC tokens were minted to `recipient`.

        The actual ASA transfer is done off-chain by algokit-utils using
        the manager's private key.  This method persists the ledger entry
        so the contract acts as the canonical on-chain source of truth.

        Args:
            recipient:  Algorand address of the supplier
            amount:     Number of whole CCC tokens minted (decimals=0)
            audit_id:   Off-chain audit reference (stored for traceability)

        Returns:
            Cumulative tokens minted to this recipient
        """
        assert Txn.sender == self.admin, "Only admin can record mints"
        assert self.asset_id.value != UInt64(0), "Asset id not configured"
        assert amount.native > UInt64(0), "Amount must be positive"

        # Update per-recipient ledger
        existing = UInt64(0)
        if recipient in self.mint_ledger:
            existing = self.mint_ledger[recipient].native
        new_total = existing + amount.native
        self.mint_ledger[recipient] = ARC4UInt64(new_total)

        # Update global counter
        self.total_minted.value = self.total_minted.value + amount.native

        return ARC4UInt64(new_total)

    # ═══════════════════════════════════════════════════════════════════
    #  COMPLIANCE BOND (lock / release / burn)
    # ═══════════════════════════════════════════════════════════════════

    @abimethod()
    def lock_bond(
        self,
        supplier: ARC4Address,
        amount: ARC4UInt64,
        reason: ARC4String,
    ) -> ARC4UInt64:
        """
        Lock `amount` CCC tokens as a compliance bond for a supplier
        (HIGH risk: 0.60–0.79).  The actual clawback ASA transfer is
        executed off-chain; this records the bond amount on-chain.

        Returns: total bonded amount after this lock.
        """
        assert Txn.sender == self.admin, "Only admin can lock bonds"
        assert amount.native > UInt64(0), "Bond amount must be positive"

        existing = UInt64(0)
        if supplier in self.bond_ledger:
            existing = self.bond_ledger[supplier].native
        new_bond = existing + amount.native
        self.bond_ledger[supplier] = ARC4UInt64(new_bond)

        return ARC4UInt64(new_bond)

    @abimethod()
    def release_bond(
        self,
        supplier: ARC4Address,
        reason: ARC4String,
    ) -> ARC4UInt64:
        """
        Release a compliance bond back to the supplier
        (next audit scored below 0.60: improvement credit).

        Returns: amount that was released.
        """
        assert Txn.sender == self.admin, "Only admin can release bonds"
        assert supplier in self.bond_ledger, "No active bond found"

        bonded = self.bond_ledger[supplier].native
        assert bonded > UInt64(0), "Bond is already zero"

        # Clear the bond entry
        self.bond_ledger[supplier] = ARC4UInt64(0)

        return ARC4UInt64(bonded)

    @abimethod()
    def burn_bond(
        self,
        supplier: ARC4Address,
        reason: ARC4String,
    ) -> ARC4UInt64:
        """
        Permanently burn (slash) the compliance bond
        (next audit scored 0.80 or above: bond forfeited).
        The off-chain layer clawbacks the tokens to the zero address.

        Returns: amount that was burned.
        """
        assert Txn.sender == self.admin, "Only admin can burn bonds"
        assert supplier in self.bond_ledger, "No active bond found"

        bonded = self.bond_ledger[supplier].native
        assert bonded > UInt64(0), "Bond is already zero"

        self.bond_ledger[supplier] = ARC4UInt64(0)
        self.total_burned.value = self.total_burned.value + bonded

        return ARC4UInt64(bonded)

    # ═══════════════════════════════════════════════════════════════════
    #  READ METHODS
    # ═══════════════════════════════════════════════════════════════════

    @abimethod(readonly=True)
    def get_mint_total(self, recipient: ARC4Address) -> ARC4UInt64:
        """Return cumulative tokens minted to a given address."""
        if recipient in self.mint_ledger:
            return self.mint_ledger[recipient]
        return ARC4UInt64(0)

    @abimethod(readonly=True)
    def get_bond_amount(self, supplier: ARC4Address) -> ARC4UInt64:
        """Return currently bonded tokens for a supplier."""
        if supplier in self.bond_ledger:
            return self.bond_ledger[supplier]
        return ARC4UInt64(0)

    @abimethod(readonly=True)
    def get_global_stats(self) -> arc4.Tuple[ARC4UInt64, ARC4UInt64, ARC4UInt64]:
        """Return (asset_id, total_minted, total_burned)."""
        return arc4.Tuple(
            (
                ARC4UInt64(self.asset_id.value),
                ARC4UInt64(self.total_minted.value),
                ARC4UInt64(self.total_burned.value),
            )
        )
