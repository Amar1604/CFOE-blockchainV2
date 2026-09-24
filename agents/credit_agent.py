"""
Credit Agent - Carbon credit scoring engine that runs after every audit.

Awards carbon credits and badges based on ESG risk score thresholds,
with streak bonuses for consistent low-risk performance and improvement
bonuses for significant score improvements between audits.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LEDGER_PATH = Path(__file__).resolve().parent.parent / "data" / "credit_ledger.json"

_ledger_lock = threading.Lock()


# ── Ledger persistence ────────────────────────────────────────────

def _load_ledger() -> Dict[str, Any]:
    """Load the credit ledger from disk."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LEDGER_PATH.exists():
        LEDGER_PATH.write_text("{}", encoding="utf-8")
        return {}
    try:
        content = LEDGER_PATH.read_text(encoding="utf-8").strip() or "{}"
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_ledger(ledger: Dict[str, Any]) -> None:
    """Write the credit ledger to disk."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


# ── Core scoring logic ───────────────────────────────────────────

def _base_credits_and_badge(esg_score: float) -> Tuple[int, Optional[str]]:
    """
    Determine base credits and badge from ESG risk score.

    Thresholds (lower is better):
        0.00–0.20  →  100 credits, "Green Champion"
        0.21–0.40  →   60 credits, "Eco Performer"
        0.41–0.60  →   20 credits, "In Progress"
        > 0.60     →    0 credits, no badge
    """
    if esg_score <= 0.20:
        return 100, "Green Champion"
    elif esg_score <= 0.40:
        return 60, "Eco Performer"
    elif esg_score <= 0.60:
        return 20, "In Progress"
    else:
        return 0, None


def _check_streak(audit_history: List[dict]) -> Tuple[int, Optional[str]]:
    """
    Check if the supplier has scored below 0.40 in 3 or more
    consecutive most-recent audits.

    Returns (bonus_credits, badge_or_None).
    """
    if len(audit_history) < 3:
        return 0, None

    # audit_history is stored newest-first; check the 3 most recent
    for entry in audit_history[:3]:
        if entry.get("esg_score", 1.0) >= 0.40:
            return 0, None

    return 50, "Consistency Streak"


def _check_improvement(esg_score: float, audit_history: List[dict]) -> Tuple[int, Optional[str]]:
    """
    If the supplier's ESG score improved (decreased) by more than 0.15
    compared to their previous audit, award an improvement bonus.

    Returns (bonus_credits, badge_or_None).
    """
    if not audit_history:
        return 0, None

    previous_score = audit_history[0].get("esg_score")
    if previous_score is None:
        return 0, None

    improvement = previous_score - esg_score  # positive means improvement
    if improvement > 0.15:
        return 30, "Improver"

    return 0, None


def _compute_current_streak(audit_streak: List[dict]) -> int:
    """Count how many consecutive most-recent audits scored below 0.40."""
    count = 0
    for entry in audit_streak:
        if entry.get("esg_score", 1.0) < 0.40:
            count += 1
        else:
            break
    return count


def _ensure_rich_entry(entry: dict) -> None:
    """Migrate a legacy (Prompt-1) supplier entry to the rich schema
    in-place.  Safe to call multiple times (idempotent)."""
    entry.setdefault("total_credits", 0)
    entry.setdefault("badge_history", [])
    entry.setdefault("audit_streak", [])
    entry.setdefault("current_streak", 0)
    entry.setdefault("longest_streak", 0)
    entry.setdefault("best_esg_score", None)
    entry.setdefault("worst_esg_score", None)
    entry.setdefault("total_audits", 0)
    entry.setdefault("credit_history", [])


# ── Public API ────────────────────────────────────────────────────

def calculate_carbon_credits(audit_result: dict) -> dict:
    """
    Calculate carbon credits for a completed audit and persist to ledger.

    Args:
        audit_result: The full audit result dict (must contain at minimum
                      ``supplier_name`` and ``risk_score``).

    Returns:
        dict with keys: supplier_id, supplier_name, credits_earned,
        badges_earned, streak_bonus, improvement_bonus, total_credits,
        previous_total, new_total, esg_score, timestamp.
    """
    supplier_name: str = audit_result.get("supplier_name", "Unknown")
    # Normalise to a stable key
    supplier_id: str = supplier_name.strip().lower().replace(" ", "_")
    esg_score: float = audit_result.get("risk_score", 1.0)
    now_iso = datetime.now(timezone.utc).isoformat()

    with _ledger_lock:
        ledger = _load_ledger()

        # Ensure supplier entry exists
        if supplier_id not in ledger:
            ledger[supplier_id] = {
                "supplier_name": supplier_name,
                "total_credits": 0,
                "badge_history": [],
                "audit_streak": [],
            }

        supplier_entry = ledger[supplier_id]
        # Migrate to rich schema if needed
        _ensure_rich_entry(supplier_entry)
        # Always keep the latest display name
        supplier_entry["supplier_name"] = supplier_name
        previous_total: int = supplier_entry["total_credits"]
        audit_history: List[dict] = supplier_entry["audit_streak"]  # newest-first

        # 1. Base credits & badge
        base_credits, base_badge = _base_credits_and_badge(esg_score)
        badges_earned: List[str] = []
        if base_badge:
            badges_earned.append(base_badge)

        # 2. Streak bonus (uses history *before* this audit is appended)
        #    We need at least 2 previous audits + current to form 3 consecutive.
        #    So we temporarily prepend the current score to check.
        temp_history = [{"esg_score": esg_score}] + audit_history
        streak_bonus, streak_badge = _check_streak(temp_history)
        if streak_badge:
            badges_earned.append(streak_badge)

        # 3. Improvement bonus (compares to most recent *previous* audit)
        improvement_bonus, improvement_badge = _check_improvement(esg_score, audit_history)
        if improvement_badge:
            badges_earned.append(improvement_badge)

        # Totals
        credits_earned = base_credits + streak_bonus + improvement_bonus
        new_total = previous_total + credits_earned

        # Update ledger
        supplier_entry["total_credits"] = new_total

        # Append audit record to streak (newest-first)
        supplier_entry["audit_streak"].insert(0, {
            "esg_score": esg_score,
            "credits_earned": credits_earned,
            "badges": badges_earned,
            "timestamp": now_iso,
        })

        # Append earned badges to badge history
        for badge in badges_earned:
            supplier_entry["badge_history"].append({
                "badge": badge,
                "timestamp": now_iso,
            })

        # ── Rich tracking fields ──────────────────────────────────
        supplier_entry["total_audits"] = supplier_entry.get("total_audits", 0) + 1

        # Current streak (recalculate from the now-updated audit_streak)
        supplier_entry["current_streak"] = _compute_current_streak(
            supplier_entry["audit_streak"]
        )

        # Longest streak ever
        cur_streak = supplier_entry["current_streak"]
        prev_longest = supplier_entry.get("longest_streak", 0)
        supplier_entry["longest_streak"] = max(prev_longest, cur_streak)

        # Best / worst ESG score
        prev_best = supplier_entry.get("best_esg_score")
        prev_worst = supplier_entry.get("worst_esg_score")
        supplier_entry["best_esg_score"] = (
            min(prev_best, esg_score) if prev_best is not None else esg_score
        )
        supplier_entry["worst_esg_score"] = (
            max(prev_worst, esg_score) if prev_worst is not None else esg_score
        )

        # Credit history entry (with running total = rank-friendly)
        supplier_entry.setdefault("credit_history", [])
        supplier_entry["credit_history"].append({
            "credits_earned": credits_earned,
            "running_total": new_total,
            "esg_score": esg_score,
            "badges": badges_earned,
            "streak_bonus": streak_bonus,
            "improvement_bonus": improvement_bonus,
            "timestamp": now_iso,
        })

        _save_ledger(ledger)

    result = {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "credits_earned": base_credits,
        "badges_earned": badges_earned,
        "streak_bonus": streak_bonus,
        "improvement_bonus": improvement_bonus,
        "total_credits": credits_earned,
        "previous_total": previous_total,
        "new_total": new_total,
        "esg_score": esg_score,
        "timestamp": now_iso,
    }

    # ── Part 2: Mint CCC ASA tokens on-chain ─────────────────────────────
    # Only mint whole positive amounts; scoring logic above is NOT touched.
    # Use SDK directly — no LLM involved.
    if credits_earned > 0:
        try:
            from onchain_ops import mint_or_queue
            from blockchain_client import get_blockchain_client

            bc             = get_blockchain_client()
            wallet_address = bc.address if bc.wallet_connected else None
            audit_id       = audit_result.get("audit_id", f"AUD-{supplier_id}")

            mint_result = mint_or_queue(
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                amount=credits_earned,
                audit_id=audit_id,
                esg_score=esg_score,
                wallet_address=wallet_address,
            )
            result["ccc_mint"] = mint_result
        except Exception as _mint_exc:
            import logging
            logging.getLogger(__name__).warning(
                f"[CreditAgent] CCC mint skipped: {_mint_exc}"
            )
            result["ccc_mint"] = {"status": "skipped", "reason": str(_mint_exc)}
    else:
        result["ccc_mint"] = {"status": "skipped", "reason": "no credits earned"}

    return result


def get_supplier_credits(supplier_id: str) -> Optional[dict]:
    """
    Return the full credit history for a single supplier.

    Returns None if the supplier is not found in the ledger.
    """
    with _ledger_lock:
        ledger = _load_ledger()

    entry = ledger.get(supplier_id)
    if entry is None:
        return None

    _ensure_rich_entry(entry)

    return {
        "supplier_id": supplier_id,
        "supplier_name": entry["supplier_name"],
        "total_credits": entry["total_credits"],
        "badge_history": entry["badge_history"],
        "audit_streak": entry["audit_streak"],
        "current_streak": entry["current_streak"],
        "longest_streak": entry["longest_streak"],
        "best_esg_score": entry["best_esg_score"],
        "worst_esg_score": entry["worst_esg_score"],
        "total_audits": entry["total_audits"],
    }


def get_supplier_credit_history(supplier_id: str) -> Optional[dict]:
    """
    Return a rich credit history payload for the supplier, designed for
    sparkline charts, badge timelines, streak history, and ESG trend.

    Returns None if the supplier is not found in the ledger.
    """
    with _ledger_lock:
        ledger = _load_ledger()

    entry = ledger.get(supplier_id)
    if entry is None:
        return None

    _ensure_rich_entry(entry)

    # credit_history is appended oldest-first (chronological)
    credit_history = entry.get("credit_history", [])

    # Credits per audit over time (for sparkline chart)
    credits_over_time = [
        {
            "credits_earned": ch["credits_earned"],
            "running_total": ch["running_total"],
            "timestamp": ch["timestamp"],
        }
        for ch in credit_history
    ]

    # ESG score trend (chronological)
    esg_trend = [
        {
            "esg_score": ch["esg_score"],
            "timestamp": ch["timestamp"],
        }
        for ch in credit_history
    ]

    # Badge timeline (already chronological in badge_history)
    badge_timeline = entry.get("badge_history", [])

    # Streak history: walk the audit_streak (newest-first) and build
    # a list of streak segments with start/end timestamps and length.
    streak_segments: List[dict] = []
    audit_streak = entry.get("audit_streak", [])
    # audit_streak is newest-first; reverse to walk chronologically
    chronological = list(reversed(audit_streak))
    current_seg_start = None
    current_seg_len = 0
    for rec in chronological:
        if rec.get("esg_score", 1.0) < 0.40:
            if current_seg_start is None:
                current_seg_start = rec["timestamp"]
            current_seg_len += 1
        else:
            if current_seg_len > 0:
                streak_segments.append({
                    "start": current_seg_start,
                    "end": chronological[
                        chronological.index(rec) - 1
                    ]["timestamp"] if current_seg_len > 0 else current_seg_start,
                    "length": current_seg_len,
                })
            current_seg_start = None
            current_seg_len = 0
    # Flush trailing segment
    if current_seg_len > 0 and chronological:
        streak_segments.append({
            "start": current_seg_start,
            "end": chronological[-1]["timestamp"],
            "length": current_seg_len,
        })

    return {
        "supplier_id": supplier_id,
        "supplier_name": entry["supplier_name"],
        "total_credits": entry["total_credits"],
        "total_audits": entry["total_audits"],
        "current_streak": entry["current_streak"],
        "longest_streak": entry["longest_streak"],
        "best_esg_score": entry["best_esg_score"],
        "worst_esg_score": entry["worst_esg_score"],
        "credits_over_time": credits_over_time,
        "esg_trend": esg_trend,
        "badge_timeline": badge_timeline,
        "streak_history": streak_segments,
    }


def get_leaderboard() -> List[dict]:
    """
    Return all suppliers sorted by total credits descending,
    with their badges and latest ESG score.
    """
    with _ledger_lock:
        ledger = _load_ledger()

    board: List[dict] = []
    for sid, entry in ledger.items():
        _ensure_rich_entry(entry)

        latest_esg = None
        if entry.get("audit_streak"):
            latest_esg = entry["audit_streak"][0].get("esg_score")

        # Unique badges earned (de-duplicated, order preserved)
        seen = set()
        unique_badges = []
        for bh in entry.get("badge_history", []):
            b = bh["badge"]
            if b not in seen:
                seen.add(b)
                unique_badges.append(b)

        board.append({
            "supplier_id": sid,
            "supplier_name": entry["supplier_name"],
            "total_credits": entry["total_credits"],
            "badges": unique_badges,
            "latest_esg_score": latest_esg,
            "current_streak": entry["current_streak"],
            "longest_streak": entry["longest_streak"],
            "total_audits": entry["total_audits"],
            "best_esg_score": entry["best_esg_score"],
        })

    board.sort(key=lambda x: x["total_credits"], reverse=True)
    return board
