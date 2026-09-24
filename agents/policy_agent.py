"""
Policy Agent - Human-in-the-Loop compliance enforcement
Part 3: Compliance bond enforcement for HIGH risk suppliers (0.60–0.79)
"""

from config.agent_framework import LLMAgent, DeterministicAgent
from config.groq_config import MODEL_LLAMA

def enforce_policy_hitl(risk_score: float, supplier_name: str) -> dict:
    """
    Enforce compliance policy with Human-in-the-Loop for critical risks
    
    Args:
        risk_score: ESG risk score (0.0-1.0)
        supplier_name: Name of the supplier
        
    Returns:
        dict with policy decision and human_approval_required flag
    """
    
    # CRITICAL: >= 0.70 requires human approval (aligned with Critical Risk classification)
    if risk_score >= 0.7:
        return {
            "decision": "ESCALATE_TO_HUMAN_REVIEW",
            "human_approval_required": True,
            "reason": f"Risk score {risk_score} exceeds critical threshold (0.70). Manual review mandatory.",
            "recommended_action": "Suspend new orders pending compliance review and executive approval"
        }
    elif risk_score >= 0.4:
        return {
            "decision": "FLAGGED - Enhanced Monitoring",
            "human_approval_required": False,
            "reason": f"Moderate risk detected (score: {risk_score}). Increased oversight recommended.",
            "recommended_action": "Implement quarterly audits and improvement plan"
        }
    else:
        return {
            "decision": "APPROVED - Standard Monitoring",
            "human_approval_required": False,
            "reason": f"Low risk detected (score: {risk_score}). Continue normal operations.",
            "recommended_action": "Maintain annual audit schedule"
        }


def enforce_compliance_bond_for_supplier(
    risk_score: float,
    supplier_id: str,
    supplier_name: str,
    audit_id: str,
    wallet_address=None,
) -> dict:
    """
    Part 3: Enforce compliance bond for HIGH risk suppliers.

    HIGH risk band: 0.60 ≤ risk_score < 0.80
      → Lock 50 CCC tokens from supplier's wallet (clawback).
    
    If a bond already exists for this supplier:
      score < 0.60  → Release bond (improvement credit)
      score >= 0.80 → Burn bond permanently (persistent non-compliance)

    All on-chain operations use the SDK via onchain_ops — never the LLM.

    Args:
        risk_score:     ESG risk score (0.0–1.0)
        supplier_id:    Normalised supplier key
        supplier_name:  Display name
        audit_id:       Audit reference
        wallet_address: Supplier's Algorand address (None if no wallet connected)

    Returns:
        Bond action dict with action, tx_id, amount, reason, timestamp.
        Empty dict if score is outside bond-relevant range and no existing bond.
    """
    # Only invoke bond logic for HIGH risk band or when a prior bond exists
    try:
        from onchain_ops import enforce_compliance_bond
        bond_result = enforce_compliance_bond(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            risk_score=risk_score,
            audit_id=audit_id,
            wallet_address=wallet_address,
        )
        return bond_result
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            f"[PolicyAgent] Bond enforcement skipped: {exc}"
        )
        return {"action": "error", "reason": str(exc)}


def policy_logic(context):
    """Execute policy enforcement logic"""
    risk_score = context.state.get('ESG_RISK_SCORE', 0)
    supplier_name = context.state.get('supplier_name', 'Unknown')
    
    policy_result = enforce_policy_hitl(risk_score, supplier_name)
    
    # Store in context
    context.state['policy_decision_outcome'] = policy_result

    # ── Part 3: Compliance bond enforcement ─────────────────────────────────
    # HIGH risk (0.60–0.79): lock 50 CCC as compliance bond
    # Runs AFTER policy decision, never changes the decision itself.
    supplier_id  = supplier_name.strip().lower().replace(" ", "_")
    audit_id     = context.state.get("audit_id", f"AUD-{supplier_id}")
    wallet_addr  = context.state.get("supplier_wallet_address")

    try:
        bond_result = enforce_compliance_bond_for_supplier(
            risk_score=risk_score,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            audit_id=audit_id,
            wallet_address=wallet_addr,
        )
        context.state["compliance_bond_result"] = bond_result
    except Exception as _bond_exc:
        context.state["compliance_bond_result"] = {
            "action": "error", "reason": str(_bond_exc)
        }
    # ── end bond enforcement ─────────────────────────────────────────────────
    
    output = f"""Policy Enforcement Complete:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Supplier: {supplier_name}
Risk Score: {risk_score}

DECISION: {policy_result['decision']}
Human Approval Required: {'YES' if policy_result['human_approval_required'] else 'NO'}

Reason: {policy_result['reason']}
Recommended Action: {policy_result['recommended_action']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    
    return output

def create_policy_agent(client=None, model_name: str = MODEL_LLAMA):
    """
    Creates the Policy Agent with HITL enforcement
    """
    
    return DeterministicAgent(
        name="PolicyAgent",
        logic_fn=policy_logic
    )

