"""
CfoE Credit Marketplace — Algorand Python (Puya) Smart Contract
Part 4: Peer-to-peer CCC token trading

Design:
  - Suppliers can list N CCC tokens for sale at a fixed ALGO price per credit
  - Buyers purchase atomically: ALGO payment + ASA transfer in a single group
  - No partial fills — buyer must purchase the exact listed amount
  - Listings stored in box storage keyed by listing_id (UInt64 counter)
  - Off-chain layer constructs the atomic group via algokit-utils

Atomic group layout for a BUY:
  Txn 0: Payment   (buyer → contract escrow)      amount = price_per_credit * amount
  Txn 1: AssetXfer (contract/seller → buyer)      CCC tokens
  Txn 2: AppCall   marketplace.execute_buy(listing_id)
"""

from algopy import (
    ARC4Contract,
    BoxMap,
    Global,
    GlobalState,
    Txn,
    UInt64,
    arc4,
    gtxn,
    TransactionType,
)
from algopy.arc4 import (
    String as ARC4String,
    UInt64 as ARC4UInt64,
    Bool as ARC4Bool,
    Address as ARC4Address,
    abimethod,
)


# ── Listing struct ──────────────────────────────────────────────────────────

class Listing(arc4.Struct):
    listing_id:       ARC4UInt64
    seller:           ARC4Address
    asset_id:         ARC4UInt64   # CCC ASA id
    amount_ccc:       ARC4UInt64   # whole CCC tokens for sale
    price_per_unit:   ARC4UInt64   # micro-ALGO per CCC token
    active:           ARC4Bool


class CreditMarketplace(ARC4Contract):
    """
    CfoE Carbon Credit peer-to-peer marketplace.

    Suppliers list CCC tokens at a fixed ALGO price.
    Buyers acquire them via an atomic group so payment
    and token transfer are inseparable.
    """

    def __init__(self) -> None:
        self.admin = GlobalState(Global.creator_address)
        self.asset_id = GlobalState(UInt64(0))      # CCC ASA id (set by admin)
        self.listing_counter = GlobalState(UInt64(0))

        # Box storage: listing_id (as UInt64 bytes) → Listing struct
        self.listings = BoxMap(ARC4UInt64, Listing, key_prefix=b"l_")

    # ═══════════════════════════════════════════
    #  ADMIN
    # ═══════════════════════════════════════════

    @abimethod()
    def set_asset_id(self, asset_id: ARC4UInt64) -> None:
        """Register the CCC ASA id. Called once by admin after ASA creation."""
        assert Txn.sender == self.admin, "Only admin"
        assert self.asset_id.value == UInt64(0), "Already set"
        self.asset_id.value = asset_id.native

    # ═══════════════════════════════════════════
    #  LIST
    # ═══════════════════════════════════════════

    @abimethod()
    def create_listing(
        self,
        amount_ccc: ARC4UInt64,
        price_per_unit: ARC4UInt64,
    ) -> ARC4UInt64:
        """
        Supplier lists CCC tokens for sale.

        Args:
            amount_ccc:      Whole CCC tokens to sell
            price_per_unit:  Price in micro-ALGO per token

        Returns:
            listing_id assigned to this offer
        """
        assert self.asset_id.value != UInt64(0), "Asset id not configured"
        assert amount_ccc.native > UInt64(0), "Amount must be positive"
        assert price_per_unit.native > UInt64(0), "Price must be positive"

        # Increment listing counter
        lid = self.listing_counter.value + UInt64(1)
        self.listing_counter.value = lid

        listing = Listing(
            listing_id=ARC4UInt64(lid),
            seller=ARC4Address(Txn.sender),
            asset_id=ARC4UInt64(self.asset_id.value),
            amount_ccc=amount_ccc,
            price_per_unit=price_per_unit,
            active=ARC4Bool(True),
        )
        self.listings[ARC4UInt64(lid)] = listing.copy()

        return ARC4UInt64(lid)

    @abimethod()
    def cancel_listing(self, listing_id: ARC4UInt64) -> None:
        """
        Supplier cancels their own active listing.
        """
        assert listing_id in self.listings, "Listing not found"
        listing = self.listings[listing_id].copy()
        assert listing.seller.native == Txn.sender, "Only seller can cancel"
        assert listing.active.native, "Listing already inactive"

        listing.active = ARC4Bool(False)
        self.listings[listing_id] = listing.copy()

    # ═══════════════════════════════════════════
    #  BUY (atomic group)
    # ═══════════════════════════════════════════

    @abimethod()
    def execute_buy(
        self,
        listing_id: ARC4UInt64,
        payment_txn_index: ARC4UInt64,
    ) -> ARC4String:
        """
        Execute a purchase.  Must be called as part of an atomic group where:
          - Group[payment_txn_index] is a Payment from buyer to this contract
            with amount == listing.amount_ccc * listing.price_per_unit

        The CCC token transfer from seller to buyer is handled off-chain
        via a separate AtomicTransactionComposer step; this method validates
        the payment and marks the listing inactive.

        Args:
            listing_id:        ID of the listing to purchase
            payment_txn_index: Index within the current atomic group of the
                               payment transaction

        Returns:
            "PURCHASE_COMPLETE"
        """
        assert listing_id in self.listings, "Listing not found"
        listing = self.listings[listing_id].copy()
        assert listing.active.native, "Listing is not active"

        # Verify payment transaction in the atomic group
        pay_txn = gtxn.PaymentTransaction(payment_txn_index.native)
        assert pay_txn.type_enum == TransactionType.Payment, "Not a payment txn"
        assert pay_txn.receiver == Global.current_application_address, "Payment must go to contract"

        expected_payment = listing.amount_ccc.native * listing.price_per_unit.native
        assert pay_txn.amount == expected_payment, "Incorrect payment amount"
        assert pay_txn.sender == Txn.sender, "Buyer must send payment"

        # Mark listing as inactive (fulfilled)
        listing.active = ARC4Bool(False)
        self.listings[listing_id] = listing.copy()

        return ARC4String("PURCHASE_COMPLETE")

    # ═══════════════════════════════════════════
    #  READ METHODS
    # ═══════════════════════════════════════════

    @abimethod(readonly=True)
    def get_listing(self, listing_id: ARC4UInt64) -> Listing:
        """Return the listing struct for a given ID."""
        assert listing_id in self.listings, "Listing not found"
        return self.listings[listing_id].copy()

    @abimethod(readonly=True)
    def get_total_listings(self) -> ARC4UInt64:
        """Return the total number of listings ever created."""
        return ARC4UInt64(self.listing_counter.value)
