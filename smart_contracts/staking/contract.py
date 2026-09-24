"""
CfoE CCC Staking Contract — Algorand Python (Puya) Smart Contract
Part 5: 30-day staking with 10% ALGO yield

Mechanics:
  - Suppliers lock CCC tokens for 30 days (2_592_000 seconds)
  - After lock period: earn 10% of staked amount paid in ALGO from treasury
  - stake()       — lock CCC tokens, record unlock timestamp
  - unstake()     — retrieve CCC tokens after lock period expires
  - claim_yield() — collect ALGO yield after lock period

Treasury ALGO is pre-funded by admin into the contract account.
The CCC transfer in/out is handled off-chain by algokit-utils using
the staker's signed atomic group; the contract validates timestamps
and records the stake positions.
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
    UInt64 as ARC4UInt64,
    Bool as ARC4Bool,
    Address as ARC4Address,
    abimethod,
)


LOCK_PERIOD_SECONDS = UInt64(2_592_000)   # 30 days
YIELD_BASIS_POINTS  = UInt64(1_000)       # 10 % = 1000 / 10_000
ALGO_YIELD_SCALE    = UInt64(10_000)


# ── Stake position struct ───────────────────────────────────────────────────

class StakePosition(arc4.Struct):
    staker:         ARC4Address
    amount_ccc:     ARC4UInt64   # tokens staked (whole CCC)
    stake_time:     ARC4UInt64   # Unix timestamp when staked
    unlock_time:    ARC4UInt64   # stake_time + LOCK_PERIOD_SECONDS
    claimed:        ARC4Bool     # yield already claimed?
    unstaked:       ARC4Bool     # tokens already returned?


class CCCStaking(ARC4Contract):
    """
    CfoE CCC Token Staking Contract.

    Suppliers deposit CCC tokens for 30 days and earn 10% ALGO yield.
    """

    def __init__(self) -> None:
        self.admin = GlobalState(Global.creator_address)
        self.asset_id = GlobalState(UInt64(0))       # CCC ASA id
        self.total_staked = GlobalState(UInt64(0))   # current total staked tokens

        # Box: staker_address → StakePosition
        self.stakes = BoxMap(ARC4Address, StakePosition, key_prefix=b"sk_")

    # ═══════════════════════════════════════════
    #  ADMIN
    # ═══════════════════════════════════════════

    @abimethod()
    def set_asset_id(self, asset_id: ARC4UInt64) -> None:
        """Register the CCC ASA id. Called once by admin."""
        assert Txn.sender == self.admin, "Only admin"
        assert self.asset_id.value == UInt64(0), "Already configured"
        self.asset_id.value = asset_id.native

    # ═══════════════════════════════════════════
    #  STAKE
    # ═══════════════════════════════════════════

    @abimethod()
    def stake(
        self,
        amount_ccc: ARC4UInt64,
    ) -> ARC4UInt64:
        """
        Record a new stake position for the caller.

        The CCC ASA transfer from staker → contract is executed off-chain
        as an AtomicTransactionComposer step paired with this app call.
        This method records the position and the unlock timestamp.

        Args:
            amount_ccc:  Whole CCC tokens to stake

        Returns:
            Unix timestamp when tokens unlock
        """
        assert self.asset_id.value != UInt64(0), "Asset not configured"
        assert amount_ccc.native > UInt64(0), "Amount must be positive"

        # Only one active stake per address
        staker_addr = ARC4Address(Txn.sender)
        if staker_addr in self.stakes:
            existing = self.stakes[staker_addr].copy()
            assert existing.unstaked.native, "Already has an active stake"

        now        = Global.latest_timestamp
        unlock_ts  = now + LOCK_PERIOD_SECONDS

        pos = StakePosition(
            staker=staker_addr,
            amount_ccc=amount_ccc,
            stake_time=ARC4UInt64(now),
            unlock_time=ARC4UInt64(unlock_ts),
            claimed=ARC4Bool(False),
            unstaked=ARC4Bool(False),
        )
        self.stakes[staker_addr] = pos.copy()
        self.total_staked.value = self.total_staked.value + amount_ccc.native

        return ARC4UInt64(unlock_ts)

    # ═══════════════════════════════════════════
    #  UNSTAKE
    # ═══════════════════════════════════════════

    @abimethod()
    def unstake(self) -> ARC4UInt64:
        """
        Mark stake as unstaked after lock period expires.

        The CCC ASA transfer from contract → staker is executed off-chain.
        This method validates the lock period and marks the position closed.

        Returns:
            Amount of CCC tokens to return to the staker.
        """
        staker_addr = ARC4Address(Txn.sender)
        assert staker_addr in self.stakes, "No stake found"

        pos = self.stakes[staker_addr].copy()
        assert not pos.unstaked.native, "Already unstaked"
        assert Global.latest_timestamp >= pos.unlock_time.native, "Lock period not yet expired"

        pos.unstaked = ARC4Bool(True)
        self.stakes[staker_addr] = pos.copy()
        self.total_staked.value = self.total_staked.value - pos.amount_ccc.native

        return pos.amount_ccc

    # ═══════════════════════════════════════════
    #  CLAIM YIELD
    # ═══════════════════════════════════════════

    @abimethod()
    def claim_yield(self) -> ARC4UInt64:
        """
        Claim the 10% ALGO yield after lock period.

        Transfers ALGO from contract treasury to the staker.
        yield_algo = (amount_ccc * 10%) expressed as micro-ALGO.
        We treat 1 CCC = 1_000_000 micro-ALGO for yield calculation
        so yield = amount_ccc * 1_000_000 * 10 / 100.

        Returns:
            Micro-ALGO amount of yield paid.
        """
        staker_addr = ARC4Address(Txn.sender)
        assert staker_addr in self.stakes, "No stake found"

        pos = self.stakes[staker_addr].copy()
        assert not pos.claimed.native, "Yield already claimed"
        assert Global.latest_timestamp >= pos.unlock_time.native, "Lock period not expired"

        # 10% yield: yield_microalgo = amount_ccc * 100_000 (= 0.1 ALGO per CCC)
        yield_micro = pos.amount_ccc.native * UInt64(100_000)

        pos.claimed = ARC4Bool(True)
        self.stakes[staker_addr] = pos.copy()

        # Inner transaction: pay yield from contract to staker
        from algopy import itxn as _itxn
        _itxn.Payment(
            receiver=Txn.sender,
            amount=yield_micro,
            fee=UInt64(0),
        ).submit()

        return ARC4UInt64(yield_micro)

    # ═══════════════════════════════════════════
    #  READ METHODS
    # ═══════════════════════════════════════════

    @abimethod(readonly=True)
    def get_stake(self, staker: ARC4Address) -> StakePosition:
        """Return stake position for a given staker address."""
        assert staker in self.stakes, "No stake found"
        return self.stakes[staker].copy()

    @abimethod(readonly=True)
    def get_total_staked(self) -> ARC4UInt64:
        """Return total CCC tokens currently staked in the contract."""
        return ARC4UInt64(self.total_staked.value)

    @abimethod(readonly=True)
    def get_pending_yield(self, staker: ARC4Address) -> ARC4UInt64:
        """
        Return pending ALGO yield (micro-ALGO) for a staker.
        Returns 0 if already claimed or lock not yet expired.
        """
        if staker not in self.stakes:
            return ARC4UInt64(0)
        pos = self.stakes[staker].copy()
        if pos.claimed.native:
            return ARC4UInt64(0)
        if Global.latest_timestamp < pos.unlock_time.native:
            return ARC4UInt64(0)
        yield_micro = pos.amount_ccc.native * UInt64(100_000)
        return ARC4UInt64(yield_micro)
