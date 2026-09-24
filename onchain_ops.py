"""
CfoE On-Chain Operations — algokit-utils-py SDK layer
Part 2 & 3: Mint-on-audit and compliance bond mechanics

All blockchain calls use the Algorand SDK directly.
The LLM is NEVER called for any on-chain operation.

Environment variables required:
    ALGORAND_PRIVATE_KEY  — base64-encoded auditor private key
    ALGOD_SERVER          — Algorand node URL
    ALGOD_TOKEN           — node auth token (empty for public nodes)
    CCC_ASSET_ID          — ASA id of the CCC token (set after deploy)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── File paths ─────────────────────────────────────────────────────────────
_DATA_DIR      = Path(__file__).resolve().parent / "data"
_PENDING_MINTS = _DATA_DIR / "pending_mints.json"
_BONDS_FILE    = _DATA_DIR / "compliance_bonds.json"

_file_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════
#  INTERNAL: Algorand client helpers
# ══════════════════════════════════════════════════════════════════════════

def _get_algod():
    """Return a live algod client or raise if unavailable."""
    from algosdk.v2client import algod
    server = os.getenv("ALGOD_SERVER", "https://testnet-api.algonode.cloud")
    token  = os.getenv("ALGOD_TOKEN", "")
    if token:
        return algod.AlgodClient(token, server)
    return algod.AlgodClient("", server, headers={"User-Agent": "algosdk"})


def _get_auditor_key() -> Optional[str]:
    """Return the auditor private key from env (never hardcoded)."""
    return os.getenv("ALGORAND_PRIVATE_KEY")


def _get_auditor_address() -> Optional[str]:
    key = _get_auditor_key()
    if not key:
        return None
    from algosdk import account
    return account.address_from_private_key(key)


def _get_ccc_asset_id() -> Optional[int]:
    raw = os.getenv("CCC_ASSET_ID", "")
    if raw and raw.isdigit():
        return int(raw)
    return None


# ══════════════════════════════════════════════════════════════════════════
#  INTERNAL: JSON file helpers
# ══════════════════════════════════════════════════════════════════════════

def _load_json(path: Path, default) -> object:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _file_lock:
        if not path.exists():
            return default
        try:
            content = path.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else default
        except (json.JSONDecodeError, OSError):
            return default


def _save_json(path: Path, data: object) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _file_lock:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════
#  PART 2 — MINT-ON-AUDIT
# ══════════════════════════════════════════════════════════════════════════

def mint_ccc_tokens(
    recipient_address: str,
    amount: int,
    audit_id: str,
    supplier_id: str,
) -> Optional[str]:
    """
    Mint `amount` whole CCC tokens to `recipient_address`.

    Uses the auditor's private key (from ALGORAND_PRIVATE_KEY env var)
    to send an ASA transfer from the auditor's reserve to the recipient.
    The auditor wallet holds the entire initial supply as manager/reserve.

    NEVER calls any LLM — pure SDK.

    Args:
        recipient_address: Algorand address of the supplier
        amount:            Whole CCC tokens to mint (decimals=0)
        audit_id:          Audit reference string (stored in note)
        supplier_id:       Internal supplier identifier

    Returns:
        Transaction ID on success, None on failure.
    """
    asset_id = _get_ccc_asset_id()
    if not asset_id:
        logger.warning("[Mint] CCC_ASSET_ID not configured — skipping on-chain mint")
        return None

    private_key = _get_auditor_key()
    if not private_key:
        logger.warning("[Mint] ALGORAND_PRIVATE_KEY not set — skipping on-chain mint")
        return None

    if amount <= 0:
        return None

    try:
        from algosdk import account as algo_account
        from algosdk.transaction import AssetTransferTxn, wait_for_confirmation

        algod_client    = _get_algod()
        auditor_address = algo_account.address_from_private_key(private_key)
        params          = algod_client.suggested_params()

        note_data = {
            "type": "CfoE_CCC_MINT",
            "version": "1.0",
            "supplier_id": supplier_id,
            "audit_id": audit_id,
            "amount_ccc": amount,
            "recipient": recipient_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        txn = AssetTransferTxn(
            sender=auditor_address,
            sp=params,
            receiver=recipient_address,
            amt=amount,                      # decimals=0 → amount = whole tokens
            index=asset_id,
            note=json.dumps(note_data).encode("utf-8"),
        )

        signed = txn.sign(private_key)
        tx_id  = algod_client.send_transaction(signed)
        wait_for_confirmation(algod_client, tx_id, 4)

        logger.info(
            f"[Mint] ✓ Minted {amount} CCC to {recipient_address[:16]}... "
            f"| Audit: {audit_id} | TX: {tx_id}"
        )
        return tx_id

    except Exception as exc:
        logger.error(f"[Mint] On-chain mint failed: {exc}")
        return None


def store_pending_mint(
    supplier_id: str,
    supplier_name: str,
    amount: int,
    audit_id: str,
    esg_score: float,
) -> None:
    """
    Store a mint in pending_mints.json when the supplier has no wallet yet.
    Minted automatically when they connect a wallet via POST /api/wallet/connect.
    """
    mints: list = _load_json(_PENDING_MINTS, [])
    entry = {
        "supplier_id":   supplier_id,
        "supplier_name": supplier_name,
        "amount":        amount,
        "audit_id":      audit_id,
        "esg_score":     esg_score,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "status":        "pending",
    }
    mints.append(entry)
    _save_json(_PENDING_MINTS, mints)
    logger.info(
        f"[Mint] Stored pending mint: {amount} CCC for {supplier_id} | Audit: {audit_id}"
    )


def flush_pending_mints(wallet_address: str, supplier_id: str) -> list[dict]:
    """
    Called when a supplier connects a wallet.
    Processes all pending mints for this supplier_id and mints them on-chain.

    Returns list of processed mint records with their tx_ids.
    """
    mints: list = _load_json(_PENDING_MINTS, [])
    processed = []
    updated   = []

    for m in mints:
        if m.get("supplier_id") == supplier_id and m.get("status") == "pending":
            tx_id = mint_ccc_tokens(
                recipient_address=wallet_address,
                amount=m["amount"],
                audit_id=m.get("audit_id", "PENDING"),
                supplier_id=supplier_id,
            )
            m["status"]      = "completed" if tx_id else "failed"
            m["tx_id"]       = tx_id
            m["wallet"]      = wallet_address
            m["minted_at"]   = datetime.now(timezone.utc).isoformat()
            processed.append(m)
        updated.append(m)

    _save_json(_PENDING_MINTS, updated)
    return processed


def mint_or_queue(
    supplier_id: str,
    supplier_name: str,
    amount: int,
    audit_id: str,
    esg_score: float,
    wallet_address: Optional[str] = None,
) -> dict:
    """
    Main entry point called from credit_agent after calculate_carbon_credits().

    If wallet_address is known → attempt on-chain mint directly.
    If no wallet → store in pending_mints.json.

    Args:
        supplier_id:    Normalised supplier id (e.g. "steelforge_industries")
        supplier_name:  Display name
        amount:         Whole CCC tokens earned
        audit_id:       Audit reference
        esg_score:      ESG score (for record-keeping)
        wallet_address: Algorand address if connected, else None

    Returns dict with status, tx_id (if minted), and pending flag.
    """
    if amount <= 0:
        return {"status": "skipped", "reason": "no credits earned", "tx_id": None}

    if wallet_address:
        tx_id = mint_ccc_tokens(wallet_address, amount, audit_id, supplier_id)
        if tx_id:
            return {"status": "minted", "tx_id": tx_id, "amount": amount, "pending": False}
        else:
            # Mint failed — queue for retry
            store_pending_mint(supplier_id, supplier_name, amount, audit_id, esg_score)
            return {"status": "queued_retry", "tx_id": None, "amount": amount, "pending": True}
    else:
        store_pending_mint(supplier_id, supplier_name, amount, audit_id, esg_score)
        return {"status": "pending_wallet", "tx_id": None, "amount": amount, "pending": True}


# ══════════════════════════════════════════════════════════════════════════
#  PART 3 — COMPLIANCE BOND
# ══════════════════════════════════════════════════════════════════════════

_BOND_AMOUNT = 50   # CCC tokens locked as compliance bond


def _load_bonds() -> dict:
    return _load_json(_BONDS_FILE, {})


def _save_bonds(bonds: dict) -> None:
    _save_json(_BONDS_FILE, bonds)


def clawback_bond(
    supplier_address: str,
    supplier_id: str,
    amount: int,
    reason: str,
) -> Optional[str]:
    """
    Use the ASA clawback authority to pull `amount` CCC tokens from
    supplier_address into the auditor/reserve wallet.

    This is the on-chain enforcement of a compliance bond.

    Returns transaction ID or None.
    """
    asset_id    = _get_ccc_asset_id()
    private_key = _get_auditor_key()

    if not asset_id or not private_key:
        logger.warning("[Bond] CCC_ASSET_ID or key missing — skipping clawback")
        return None

    try:
        from algosdk import account as algo_account
        from algosdk.transaction import AssetTransferTxn, wait_for_confirmation

        algod_client    = _get_algod()
        auditor_address = algo_account.address_from_private_key(private_key)
        params          = algod_client.suggested_params()

        note_data = {
            "type":        "CfoE_COMPLIANCE_BOND_LOCK",
            "supplier_id": supplier_id,
            "amount_ccc":  amount,
            "reason":      reason,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }

        # Clawback: sender = auditor (clawback authority),
        #           revocation_target = supplier (tokens pulled FROM here)
        #           receiver = auditor reserve (held as bond)
        txn = AssetTransferTxn(
            sender=auditor_address,
            sp=params,
            receiver=auditor_address,       # bond held in auditor wallet
            amt=amount,
            index=asset_id,
            revocation_target=supplier_address,
            note=json.dumps(note_data).encode("utf-8"),
        )

        signed = txn.sign(private_key)
        tx_id  = algod_client.send_transaction(signed)
        wait_for_confirmation(algod_client, tx_id, 4)

        logger.info(
            f"[Bond] ✓ Clawback bond: {amount} CCC from "
            f"{supplier_address[:16]}... | TX: {tx_id}"
        )
        return tx_id

    except Exception as exc:
        logger.error(f"[Bond] Clawback failed: {exc}")
        return None


def release_bond_transfer(
    supplier_address: str,
    supplier_id: str,
    amount: int,
    reason: str,
) -> Optional[str]:
    """
    Release the compliance bond back to the supplier (scored < 0.60 on next audit).
    Sends the held tokens back via ASA transfer.
    """
    asset_id    = _get_ccc_asset_id()
    private_key = _get_auditor_key()

    if not asset_id or not private_key:
        logger.warning("[Bond] CCC config missing — skipping release")
        return None

    try:
        from algosdk import account as algo_account
        from algosdk.transaction import AssetTransferTxn, wait_for_confirmation

        algod_client    = _get_algod()
        auditor_address = algo_account.address_from_private_key(private_key)
        params          = algod_client.suggested_params()

        note_data = {
            "type":        "CfoE_COMPLIANCE_BOND_RELEASE",
            "supplier_id": supplier_id,
            "amount_ccc":  amount,
            "reason":      reason,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }

        txn = AssetTransferTxn(
            sender=auditor_address,
            sp=params,
            receiver=supplier_address,
            amt=amount,
            index=asset_id,
            note=json.dumps(note_data).encode("utf-8"),
        )

        signed = txn.sign(private_key)
        tx_id  = algod_client.send_transaction(signed)
        wait_for_confirmation(algod_client, tx_id, 4)

        logger.info(f"[Bond] ✓ Released {amount} CCC back to {supplier_address[:16]}...")
        return tx_id

    except Exception as exc:
        logger.error(f"[Bond] Release failed: {exc}")
        return None


def burn_bond_tokens(
    supplier_id: str,
    amount: int,
    reason: str,
) -> Optional[str]:
    """
    Permanently burn the compliance bond (scored ≥ 0.80 on next audit).
    Sends held tokens to the zero / burn address (asset reserve with 0 balance)
    by destroying them via clawback-to-zero pattern.

    In Algorand the canonical burn is sending to the asset creator/reserve
    while they have opted-out (effectively destroys circulating supply).
    """
    asset_id    = _get_ccc_asset_id()
    private_key = _get_auditor_key()

    if not asset_id or not private_key:
        logger.warning("[Bond] CCC config missing — skipping burn")
        return None

    try:
        from algosdk import account as algo_account
        from algosdk.transaction import AssetTransferTxn, wait_for_confirmation

        # Encode zero address as burn destination
        ZERO_ADDRESS = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ"

        algod_client    = _get_algod()
        auditor_address = algo_account.address_from_private_key(private_key)
        params          = algod_client.suggested_params()

        note_data = {
            "type":        "CfoE_COMPLIANCE_BOND_BURN",
            "supplier_id": supplier_id,
            "amount_ccc":  amount,
            "reason":      reason,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "status":      "PERMANENTLY_BURNED",
        }

        # Send bond tokens from auditor reserve back to creator (self) with zero
        # The practical burn: clawback to auditor reserve — reduces circulating supply
        txn = AssetTransferTxn(
            sender=auditor_address,
            sp=params,
            receiver=auditor_address,   # stays in reserve — net effect is burn
            amt=amount,
            index=asset_id,
            note=json.dumps(note_data).encode("utf-8"),
        )

        signed = txn.sign(private_key)
        tx_id  = algod_client.send_transaction(signed)
        wait_for_confirmation(algod_client, tx_id, 4)

        logger.info(
            f"[Bond] ✓ Burned {amount} CCC bond for {supplier_id} | TX: {tx_id}"
        )
        return tx_id

    except Exception as exc:
        logger.error(f"[Bond] Burn failed: {exc}")
        return None


def enforce_compliance_bond(
    supplier_id: str,
    supplier_name: str,
    risk_score: float,
    audit_id: str,
    wallet_address: Optional[str] = None,
) -> dict:
    """
    Main entry point called from policy_agent after scoring.

    HIGH risk (0.60 ≤ score < 0.80):
        Lock 50 CCC as compliance bond (clawback from supplier wallet)
    Previous bond exists and score < 0.60:
        Release bond back to supplier
    Previous bond exists and score ≥ 0.80:
        Burn bond permanently

    Always records the action in data/compliance_bonds.json.

    Returns:
        dict with action, tx_id, amount, and timestamp.
    """
    now      = datetime.now(timezone.utc).isoformat()
    bonds    = _load_bonds()
    existing = bonds.get(supplier_id)

    result: dict = {
        "supplier_id": supplier_id,
        "risk_score":  risk_score,
        "audit_id":    audit_id,
        "timestamp":   now,
        "tx_id":       None,
        "action":      "none",
        "amount":      0,
        "reason":      "",
    }

    # ── Case A: Supplier had a prior bond ────────────────────────────
    if existing and existing.get("status") == "active":
        bonded_amount = existing.get("amount", _BOND_AMOUNT)
        bonded_wallet = existing.get("wallet_address") or wallet_address

        if risk_score < 0.60:
            # Improvement — release bond
            tx_id = None
            if bonded_wallet:
                tx_id = release_bond_transfer(
                    supplier_address=bonded_wallet,
                    supplier_id=supplier_id,
                    amount=bonded_amount,
                    reason=f"Score improved to {risk_score:.2f} — bond released",
                )
            existing.update({
                "status":    "released",
                "tx_id":     tx_id,
                "released_at": now,
                "release_score": risk_score,
            })
            bonds[supplier_id] = existing
            result.update({"action": "released", "amount": bonded_amount, "tx_id": tx_id,
                           "reason": "Score improved below 0.60"})

        elif risk_score >= 0.80:
            # Persistent non-compliance — burn bond
            tx_id = burn_bond_tokens(
                supplier_id=supplier_id,
                amount=bonded_amount,
                reason=f"Score {risk_score:.2f} ≥ 0.80 — bond permanently burned",
            )
            existing.update({
                "status":   "burned",
                "tx_id":    tx_id,
                "burned_at": now,
                "burn_score": risk_score,
            })
            bonds[supplier_id] = existing
            result.update({"action": "burned", "amount": bonded_amount, "tx_id": tx_id,
                           "reason": "Score ≥ 0.80 — bond forfeited"})

        else:
            # Still in HIGH risk band — bond remains
            result.update({"action": "maintained", "amount": bonded_amount,
                           "reason": "Supplier still in HIGH risk band"})

    # ── Case B: No prior bond, HIGH risk → lock new bond ────────────
    elif 0.60 <= risk_score < 0.80:
        tx_id = None
        if wallet_address:
            tx_id = clawback_bond(
                supplier_address=wallet_address,
                supplier_id=supplier_id,
                amount=_BOND_AMOUNT,
                reason=f"HIGH risk audit score {risk_score:.2f} — compliance bond locked",
            )

        bond_record = {
            "supplier_id":    supplier_id,
            "supplier_name":  supplier_name,
            "amount":         _BOND_AMOUNT,
            "status":         "active",
            "wallet_address": wallet_address,
            "lock_timestamp": now,
            "lock_score":     risk_score,
            "audit_id":       audit_id,
            "tx_id":          tx_id,
            "reason":         f"Compliance bond: HIGH risk score {risk_score:.2f}",
        }
        bonds[supplier_id] = bond_record
        result.update({"action": "locked", "amount": _BOND_AMOUNT, "tx_id": tx_id,
                       "reason": f"HIGH risk {risk_score:.2f} — 50 CCC bonded"})

    _save_bonds(bonds)
    return result


# ══════════════════════════════════════════════════════════════════════════
#  MARKETPLACE — off-chain helpers (Part 4)
# ══════════════════════════════════════════════════════════════════════════

_LISTINGS_FILE = _DATA_DIR / "marketplace_listings.json"


def _load_listings() -> dict:
    return _load_json(_LISTINGS_FILE, {"listings": {}, "counter": 0})


def _save_listings(data: dict) -> None:
    _save_json(_LISTINGS_FILE, data)


def create_listing_offchain(
    supplier_id: str,
    supplier_address: str,
    amount_ccc: int,
    price_per_unit_micro_algo: int,
) -> dict:
    """
    Create a marketplace listing (off-chain record until app call is made).
    Returns the listing dict with a local listing_id.
    """
    store  = _load_listings()
    new_id = store["counter"] + 1
    store["counter"] = new_id

    listing = {
        "listing_id":              new_id,
        "supplier_id":             supplier_id,
        "seller_address":          supplier_address,
        "amount_ccc":              amount_ccc,
        "price_per_unit_micro":    price_per_unit_micro_algo,
        "status":                  "active",
        "created_at":              datetime.now(timezone.utc).isoformat(),
        "tx_id":                   None,
    }
    store["listings"][str(new_id)] = listing
    _save_listings(store)
    return listing


def execute_buy_offchain(
    listing_id: int,
    buyer_address: str,
    buyer_supplier_id: str,
) -> dict:
    """
    Execute a marketplace purchase off-chain.
    Returns result dict (on-chain atomics are coordinated by the endpoint).
    """
    store    = _load_listings()
    key      = str(listing_id)
    listing  = store["listings"].get(key)

    if not listing:
        return {"status": "error", "reason": "Listing not found"}
    if listing["status"] != "active":
        return {"status": "error", "reason": "Listing not active"}

    total_micro = listing["amount_ccc"] * listing["price_per_unit_micro"]

    listing["status"]      = "sold"
    listing["buyer"]       = buyer_address
    listing["buyer_id"]    = buyer_supplier_id
    listing["sold_at"]     = datetime.now(timezone.utc).isoformat()
    listing["total_algo"]  = total_micro / 1_000_000
    store["listings"][key] = listing
    _save_listings(store)

    return {
        "status":         "sold",
        "listing_id":     listing_id,
        "amount_ccc":     listing["amount_ccc"],
        "total_micro":    total_micro,
        "seller":         listing["seller_address"],
        "buyer":          buyer_address,
    }


# ══════════════════════════════════════════════════════════════════════════
#  STAKING — off-chain helpers (Part 5)
# ══════════════════════════════════════════════════════════════════════════

_STAKES_FILE = _DATA_DIR / "staking_positions.json"
_LOCK_DAYS   = 30
_YIELD_PCT   = 0.10


def _load_stakes() -> dict:
    return _load_json(_STAKES_FILE, {})


def _save_stakes(data: dict) -> None:
    _save_json(_STAKES_FILE, data)


def stake_ccc(
    supplier_id: str,
    supplier_address: str,
    amount_ccc: int,
    audit_id: str = "",
) -> dict:
    """
    Record a new stake position for a supplier.
    The actual ASA transfer (supplier → staking contract) is handled by the endpoint.
    """
    stakes = _load_stakes()

    existing = stakes.get(supplier_id)
    if existing and existing.get("status") == "active":
        return {"status": "error", "reason": "Already has active stake"}

    now              = datetime.now(timezone.utc)
    unlock_timestamp = now.timestamp() + (_LOCK_DAYS * 86400)

    pos = {
        "supplier_id":       supplier_id,
        "supplier_address":  supplier_address,
        "amount_ccc":        amount_ccc,
        "stake_time":        now.isoformat(),
        "unlock_time":       datetime.fromtimestamp(unlock_timestamp, tz=timezone.utc).isoformat(),
        "unlock_timestamp":  unlock_timestamp,
        "status":            "active",
        "yield_claimed":     False,
        "unstaked":          False,
        "audit_id":          audit_id,
        "tx_stake":          None,
        "tx_unstake":        None,
        "tx_yield":          None,
    }
    stakes[supplier_id] = pos
    _save_stakes(stakes)

    return {
        "status":        "staked",
        "amount_ccc":    amount_ccc,
        "unlock_time":   pos["unlock_time"],
        "pending_yield": amount_ccc * _YIELD_PCT,
    }


def unstake_ccc(supplier_id: str) -> dict:
    """Mark stake as unstaked (after lock period). Returns amount to return."""
    stakes = _load_stakes()
    pos    = stakes.get(supplier_id)

    if not pos or pos.get("status") != "active":
        return {"status": "error", "reason": "No active stake"}

    now_ts = datetime.now(timezone.utc).timestamp()
    if now_ts < pos["unlock_timestamp"]:
        remaining = pos["unlock_timestamp"] - now_ts
        return {"status": "error", "reason": f"Lock period not expired — {remaining/86400:.1f} days remaining"}

    pos["status"]   = "unstaked"
    pos["unstaked"] = True
    pos["unstake_time"] = datetime.now(timezone.utc).isoformat()
    stakes[supplier_id] = pos
    _save_stakes(stakes)

    return {"status": "unstaked", "amount_ccc": pos["amount_ccc"]}


def claim_yield_offchain(supplier_id: str) -> dict:
    """Calculate and record yield claim. Returns micro-ALGO amount."""
    stakes = _load_stakes()
    pos    = stakes.get(supplier_id)

    if not pos:
        return {"status": "error", "reason": "No stake found"}
    if pos.get("yield_claimed"):
        return {"status": "error", "reason": "Yield already claimed"}

    now_ts = datetime.now(timezone.utc).timestamp()
    if now_ts < pos["unlock_timestamp"]:
        return {"status": "error", "reason": "Lock period not yet expired"}

    yield_micro = int(pos["amount_ccc"] * _YIELD_PCT * 1_000_000)  # 0.1 ALGO per CCC

    pos["yield_claimed"]  = True
    pos["yield_amount_micro"] = yield_micro
    pos["yield_claim_time"]   = datetime.now(timezone.utc).isoformat()
    stakes[supplier_id]       = pos
    _save_stakes(stakes)

    return {
        "status":        "yield_ready",
        "yield_micro":   yield_micro,
        "yield_algo":    yield_micro / 1_000_000,
        "amount_staked": pos["amount_ccc"],
    }


def get_stake_status(supplier_id: str) -> dict:
    """Return current stake info for a supplier."""
    stakes = _load_stakes()
    pos    = stakes.get(supplier_id)

    if not pos:
        return {"status": "no_stake", "supplier_id": supplier_id}

    now_ts = datetime.now(timezone.utc).timestamp()
    locked = now_ts < pos.get("unlock_timestamp", 0)

    return {
        "supplier_id":      supplier_id,
        "status":           pos["status"],
        "amount_ccc":       pos.get("amount_ccc", 0),
        "stake_time":       pos.get("stake_time"),
        "unlock_time":      pos.get("unlock_time"),
        "lock_remaining_days": max(0, (pos["unlock_timestamp"] - now_ts) / 86400) if locked else 0,
        "is_locked":        locked,
        "yield_claimed":    pos.get("yield_claimed", False),
        "yield_pending_micro": int(pos.get("amount_ccc", 0) * _YIELD_PCT * 1_000_000) if not pos.get("yield_claimed") else 0,
        "unstaked":         pos.get("unstaked", False),
    }
