"""
Agent Wallet Manager — Part 1 of Agentic Commerce (X402 on Algorand)

Generates and persists a dedicated Algorand Testnet wallet for each CfoE agent:
  - monitor_agent_wallet
  - reporting_agent_wallet
  - policy_agent_wallet

Rules:
  • Wallet addresses are stored in data/agent_wallets.json
  • Private keys are stored ONLY in environment variables (never files)
  • Each wallet is funded with 5 ALGO from the main auditor wallet on first run
  • Wallet balances are logged at startup
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Any

from dotenv import load_dotenv, set_key

load_dotenv()

logger = logging.getLogger("agent_wallets")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# ── Constants ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WALLETS_PATH = DATA_DIR / "agent_wallets.json"
ENV_PATH = BASE_DIR / ".env"

AGENT_NAMES = ["monitor_agent", "reporting_agent", "policy_agent"]
FUNDING_AMOUNT_ALGO = 1.0          # ALGO per agent on first run (reduced from 5.0)
LOW_BALANCE_THRESHOLD = 0.01      # ALGO — triggers top-up request
TOP_UP_AMOUNT_ALGO = 1.0           # ALGO to top-up when balance is low (reduced from 5.0)

_wallet_lock = threading.Lock()


# ── Algod helpers ──────────────────────────────────────────────────────────

def _get_algod_client():
    """Return a connected algod client or raise ImportError."""
    from algosdk.v2client import algod  # type: ignore
    server = os.getenv("ALGOD_SERVER", "https://testnet-api.algonode.cloud")
    token = os.getenv("ALGOD_TOKEN", "")
    if token:
        return algod.AlgodClient(token, server)
    return algod.AlgodClient("", server, headers={"User-Agent": "CfoE-AgentWallets/1.0"})


def _micro_to_algo(micro: int) -> float:
    return micro / 1_000_000


def _algo_to_micro(algo: float) -> int:
    return int(algo * 1_000_000)


# ── Wallet file (addresses only — NO private keys) ─────────────────────────

def _load_wallets() -> Dict[str, Any]:
    """Load wallet addresses from data/agent_wallets.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not WALLETS_PATH.exists():
        WALLETS_PATH.write_text("{}", encoding="utf-8")
    with _wallet_lock:
        try:
            raw = WALLETS_PATH.read_text(encoding="utf-8").strip() or "{}"
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}


def _save_wallets(wallets: Dict[str, Any]) -> None:
    """Persist wallet addresses (no private keys)."""
    with _wallet_lock:
        WALLETS_PATH.write_text(json.dumps(wallets, indent=2), encoding="utf-8")


# ── Private Key helpers (env vars only) ────────────────────────────────────

def _env_key_name(agent_name: str) -> str:
    return f"AGENT_PRIVATE_KEY_{agent_name.upper()}"


def _get_private_key(agent_name: str) -> Optional[str]:
    """Retrieve agent private key from environment variable."""
    return os.getenv(_env_key_name(agent_name))


def _store_private_key(agent_name: str, private_key: str) -> None:
    """Store agent private key in .env file and current process env.

    SECURITY: Keys are stored ONLY here — never in data/*.json files.
    """
    env_var = _env_key_name(agent_name)
    os.environ[env_var] = private_key
    try:
        set_key(str(ENV_PATH), env_var, private_key)
        logger.info("Private key for %s stored in .env (env var: %s)", agent_name, env_var)
    except Exception as exc:
        logger.warning("Could not write private key to .env for %s: %s", agent_name, exc)


# ── Wallet generation ──────────────────────────────────────────────────────

def _generate_wallet(agent_name: str) -> Dict[str, str]:
    """Generate a fresh Algorand account for an agent.

    Returns: {"address": str}  — the private key is stored in env only.
    """
    from algosdk import account  # type: ignore

    private_key, address = account.generate_account()
    _store_private_key(agent_name, private_key)
    logger.info("Generated new wallet for %s: %s", agent_name, address)
    return {"address": address, "funded": False}


# ── Funding ────────────────────────────────────────────────────────────────

def _fund_wallet(
    recipient_address: str,
    amount_algo: float,
    sender_private_key: str,
    sender_address: str,
    algod_client,
    label: str = "agent",
) -> Optional[str]:
    """Send ALGO from auditor wallet to an agent wallet.

    Returns the transaction ID on success, or None on failure.
    """
    from algosdk import transaction  # type: ignore

    try:
        params = algod_client.suggested_params()
        amount_micro = _algo_to_micro(amount_algo)

        txn = transaction.PaymentTxn(
            sender=sender_address,
            sp=params,
            receiver=recipient_address,
            amt=amount_micro,
            note=f"CfoE agent wallet funding — {label}".encode("utf-8"),
        )
        signed = txn.sign(sender_private_key)
        tx_id = algod_client.send_transaction(signed)
        transaction.wait_for_confirmation(algod_client, tx_id, 4)
        logger.info(
            "Funded %s wallet %s with %.3f ALGO — TX: %s",
            label, recipient_address[:16], amount_algo, tx_id,
        )
        return tx_id
    except Exception as exc:
        logger.error("Failed to fund %s wallet: %s", label, exc)
        return None


def _get_balance_algo(address: str, algod_client) -> float:
    """Return the ALGO balance for an address (0.0 on any error)."""
    try:
        info = algod_client.account_info(address)
        return _micro_to_algo(info.get("amount", 0))
    except Exception as exc:
        logger.warning("Could not fetch balance for %s: %s", address[:16], exc)
        return 0.0


# ── Public API ─────────────────────────────────────────────────────────────

def initialize_agent_wallets() -> Dict[str, Any]:
    """
    Ensure every agent has a dedicated Algorand Testnet wallet.

    On first run:
      1. Generates a new account for each agent
      2. Persists addresses to data/agent_wallets.json
      3. Funds each wallet with FUNDING_AMOUNT_ALGO from the auditor wallet
      4. Logs every balance

    On subsequent runs:
      • Loads existing addresses from disk
      • Re-reads private keys from env vars
      • Logs balances

    Returns dict keyed by agent name with address and balance info.
    """
    wallets = _load_wallets()
    result: Dict[str, Any] = {}

    # Try to connect to Algorand for funding/balance checks
    algod_client = None
    auditor_pk = os.getenv("ALGORAND_PRIVATE_KEY")
    auditor_address = None

    try:
        algod_client = _get_algod_client()
        if auditor_pk:
            from algosdk import account as _acct  # type: ignore
            auditor_address = _acct.address_from_private_key(auditor_pk)
    except Exception as exc:
        logger.warning("Could not connect to Algorand: %s — wallets will operate in offline mode", exc)

    changed = False

    for agent_name in AGENT_NAMES:
        agent_info = wallets.get(agent_name)

        # ── Step 1: Generate wallet if missing ────────────────────────────
        if not agent_info or not agent_info.get("address"):
            agent_info = _generate_wallet(agent_name)
            wallets[agent_name] = agent_info
            changed = True
        else:
            # Wallet exists on disk — make sure private key is still in env
            pk = _get_private_key(agent_name)
            if not pk:
                logger.warning(
                    "Private key for %s not found in env — re-generating wallet!", agent_name
                )
                agent_info = _generate_wallet(agent_name)
                wallets[agent_name] = agent_info
                changed = True

        address = agent_info["address"]

        # ── Step 2: Get current balance ───────────────────────────────────
        balance = 0.0
        if algod_client:
            balance = _get_balance_algo(address, algod_client)

        # ── Step 3: Fund on first run (unfunded wallets) ──────────────────
        funded = agent_info.get("funded", False)
        funding_tx = None

        if not funded and algod_client and auditor_pk and auditor_address:
            if balance < FUNDING_AMOUNT_ALGO:
                funding_tx = _fund_wallet(
                    recipient_address=address,
                    amount_algo=FUNDING_AMOUNT_ALGO,
                    sender_private_key=auditor_pk,
                    sender_address=auditor_address,
                    algod_client=algod_client,
                    label=agent_name,
                )
                if funding_tx:
                    agent_info["funded"] = True
                    agent_info["funding_tx"] = funding_tx
                    wallets[agent_name] = agent_info
                    # Refresh balance after funding
                    time.sleep(1)
                    balance = _get_balance_algo(address, algod_client)
                    changed = True

        # ── Step 4: Log balance ───────────────────────────────────────────
        logger.info(
            "[Startup] Agent wallet %-22s | address=%s... | balance=%.6f ALGO",
            agent_name, address[:20], balance,
        )

        result[agent_name] = {
            "address": address,
            "balance_algo": balance,
            "funded": agent_info.get("funded", False),
            "funding_tx": agent_info.get("funding_tx"),
        }

    if changed:
        _save_wallets(wallets)

    return result


def get_agent_address(agent_name: str) -> Optional[str]:
    """Return the Algorand address for the given agent, or None."""
    wallets = _load_wallets()
    return wallets.get(agent_name, {}).get("address")


def get_agent_private_key(agent_name: str) -> Optional[str]:
    """Return the private key for the given agent from environment, or None."""
    return _get_private_key(agent_name)


def get_agent_balance(agent_name: str) -> float:
    """Return the current ALGO balance for the given agent (0.0 on error)."""
    address = get_agent_address(agent_name)
    if not address:
        return 0.0
    try:
        algod_client = _get_algod_client()
        return _get_balance_algo(address, algod_client)
    except Exception:
        return 0.0


def check_and_topup(agent_name: str) -> Optional[str]:
    """
    If the agent's balance is below LOW_BALANCE_THRESHOLD, request a top-up
    from the main auditor wallet (ALGORAND_PRIVATE_KEY) and log the event.

    Returns the funding TX ID on success, None otherwise.
    """
    address = get_agent_address(agent_name)
    if not address:
        logger.warning("check_and_topup: no wallet found for %s", agent_name)
        return None

    try:
        algod_client = _get_algod_client()
        balance = _get_balance_algo(address, algod_client)

        if balance >= LOW_BALANCE_THRESHOLD:
            return None  # Balance is fine

        logger.warning(
            "Agent %s balance LOW (%.6f ALGO < %.4f) — requesting top-up",
            agent_name, balance, LOW_BALANCE_THRESHOLD,
        )

        auditor_pk = os.getenv("ALGORAND_PRIVATE_KEY")
        if not auditor_pk:
            logger.error("Cannot top-up %s: ALGORAND_PRIVATE_KEY not set in .env", agent_name)
            return None

        from algosdk import account as _acct  # type: ignore
        auditor_address = _acct.address_from_private_key(auditor_pk)

        tx_id = _fund_wallet(
            recipient_address=address,
            amount_algo=TOP_UP_AMOUNT_ALGO,
            sender_private_key=auditor_pk,
            sender_address=auditor_address,
            algod_client=algod_client,
            label=f"{agent_name} top-up",
        )
        if tx_id:
            logger.info(
                "Top-up complete for %s: +%.3f ALGO (TX: %s)",
                agent_name, TOP_UP_AMOUNT_ALGO, tx_id,
            )
        return tx_id

    except Exception as exc:
        logger.error("check_and_topup failed for %s: %s", agent_name, exc)
        return None
