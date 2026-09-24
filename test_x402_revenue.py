"""
Test X402 Agentic Commerce Revenue System
==========================================

This script tests the complete X402 payment flow AFTER audits have been run:
1. Verifies agent wallets are initialized
2. Checks encrypted reports exist from completed audits
3. Tests payment recording and verification
4. Validates revenue dashboard aggregation

Run this AFTER running audits via the API to verify the X402 system.

Usage:
    python test_x402_revenue.py
"""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_result(test_name: str, passed: bool, details: str = "") -> None:
    """Print test result with color coding."""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"{status} | {test_name}")
    if details:
        print(f"       {details}")


def test_agent_wallets() -> bool:
    """Test 1: Agent wallet initialization."""
    print_section("TEST 1: Agent Wallet Initialization")
    
    try:
        from agents.agent_wallets import initialize_agent_wallets, get_agent_address, get_agent_balance
        
        # Initialize wallets
        print("Initializing agent wallets...")
        wallets = initialize_agent_wallets()
        
        # Check all three agents
        agents = ["monitor_agent", "reporting_agent", "policy_agent"]
        all_ok = True
        
        for agent in agents:
            addr = get_agent_address(agent)
            balance = get_agent_balance(agent)
            
            if addr:
                print_result(f"{agent} wallet", True, f"Address: {addr[:20]}... | Balance: {balance:.6f} ALGO")
            else:
                print_result(f"{agent} wallet", False, "No address found")
                all_ok = False
        
        return all_ok
        
    except Exception as e:
        print_result("Agent wallet initialization", False, str(e))
        return False


def test_encrypted_reports_from_audits() -> bool:
    """Test 2: Check encrypted reports exist from completed audits."""
    print_section("TEST 2: Encrypted Reports from Completed Audits")
    
    try:
        # Load audit history
        history_file = PROJECT_ROOT / "data" / "audit_history.json"
        if not history_file.exists():
            print_result("Audit history exists", False, "No audits found - run audits first!")
            return False
        
        with open(history_file, 'r') as f:
            audits = json.load(f)
        
        if len(audits) == 0:
            print_result("Audits exist", False, "No audits in history - run audits first!")
            return False
        
        print(f"Found {len(audits)} audits in history")
        
        # Load encrypted reports
        reports_file = PROJECT_ROOT / "data" / "encrypted_reports.json"
        if not reports_file.exists():
            print_result("Encrypted reports file exists", False, "No encrypted_reports.json found")
            return False
        
        with open(reports_file, 'r') as f:
            reports = json.load(f)
        
        report_count = len(reports)
        print_result("Encrypted reports exist", report_count > 0, f"Found {report_count} encrypted reports")
        
        # Check if recent audits have encrypted reports
        recent_audits = audits[:5]  # Check last 5 audits
        matched = 0
        
        for audit in recent_audits:
            audit_id = audit.get("audit_id")
            if audit_id in reports:
                matched += 1
                report = reports[audit_id]
                print_result(
                    f"Report for {audit_id}", 
                    True, 
                    f"Supplier: {report.get('supplier_name')} | Paid: {report.get('paid', False)}"
                )
        
        print(f"\n{matched}/{len(recent_audits)} recent audits have encrypted reports")
        
        return report_count > 0 and matched > 0
        
    except Exception as e:
        print_result("Encrypted reports check", False, str(e))
        return False


def test_payment_recording() -> bool:
    """Test 3: Payment recording to agent_payments.json."""
    print_section("TEST 3: Payment Recording System")
    
    try:
        from agents.x402_payments import record_payment
        
        # Record test payment
        test_tx_id = f"TEST-TX-{int(time.time())}"
        test_audit_id = f"AUD-TEST-{int(time.time())}"
        
        print("Recording test payment...")
        record = record_payment(
            agent_name="reporting_agent",
            amount_algo=0.02,
            service="report_access",
            tx_id=test_tx_id,
            direction="incoming",
            status="confirmed",
            audit_id=test_audit_id
        )
        
        # Verify record structure
        checks = [
            (record.get("agent") == "reporting_agent", "Agent: reporting_agent"),
            (record.get("amount_algo") == 0.02, "Amount: 0.02 ALGO"),
            (record.get("service") == "report_access", "Service: report_access"),
            (record.get("direction") == "incoming", "Direction: incoming"),
            (record.get("status") == "confirmed", "Status: confirmed"),
            (record.get("tx_id") == test_tx_id, f"TX ID: {test_tx_id}"),
        ]
        
        all_ok = True
        for passed, msg in checks:
            print_result(msg, passed)
            if not passed:
                all_ok = False
        
        # Verify file persistence
        payments_file = PROJECT_ROOT / "data" / "agent_payments.json"
        if payments_file.exists():
            with open(payments_file, 'r') as f:
                payments = json.load(f)
                found = any(p.get("tx_id") == test_tx_id for p in payments)
                print_result("Payment persisted to file", found)
                if not found:
                    all_ok = False
        
        return all_ok
        
    except Exception as e:
        print_result("Payment recording", False, str(e))
        return False


def test_revenue_aggregation() -> bool:
    """Test 4: Revenue dashboard aggregation."""
    print_section("TEST 4: Revenue Dashboard Aggregation")
    
    try:
        # Read payments file
        payments_file = PROJECT_ROOT / "data" / "agent_payments.json"
        
        if not payments_file.exists():
            print_result("Payments file exists", False, "No agent_payments.json found")
            return False
        
        with open(payments_file, 'r') as f:
            payments = json.load(f)
        
        print(f"Found {len(payments)} total payments in ledger")
        
        # Aggregate earnings (same logic as /api/revenue)
        agent_earnings = {}
        total_audits_paid = 0
        total_reports_sold = 0
        
        for p in payments:
            agent = p.get("agent", "unknown")
            direction = p.get("direction", "outgoing")
            amount = p.get("amount_algo", 0.0)
            service = p.get("service", "")
            status = p.get("status", "")
            
            if direction == "incoming" and status == "confirmed":
                agent_earnings[agent] = agent_earnings.get(agent, 0.0) + amount
                
                if service == "audit":
                    total_audits_paid += 1
                elif service == "report_access":
                    total_reports_sold += 1
        
        total_earned = sum(agent_earnings.values())
        
        # Display results
        print(f"\n📊 Revenue Summary:")
        print(f"   Total ALGO Earned: {total_earned:.6f} ALGO")
        print(f"   Total Audits Paid: {total_audits_paid}")
        print(f"   Total Reports Sold: {total_reports_sold}")
        
        print(f"\n💰 Earnings by Agent:")
        for agent, amount in agent_earnings.items():
            print(f"   {agent}: {amount:.6f} ALGO")
        
        # Verify calculations
        checks = [
            (len(payments) > 0, f"Payment ledger has {len(payments)} entries"),
            (total_earned >= 0, f"Total earnings: {total_earned:.6f} ALGO"),
        ]
        
        all_ok = True
        for passed, msg in checks:
            print_result(msg, passed)
            if not passed:
                all_ok = False
        
        return all_ok
        
    except Exception as e:
        print_result("Revenue aggregation", False, str(e))
        return False


def test_report_access_flow() -> bool:
    """Test 5: Complete report access flow simulation."""
    print_section("TEST 5: Report Access Flow (Using Real Audit Data)")
    
    try:
        from agents.reporting_agent import (
            get_report_blob, 
            mark_report_paid,
            get_decrypted_report
        )
        
        # Get a real audit ID from history
        history_file = PROJECT_ROOT / "data" / "audit_history.json"
        with open(history_file, 'r') as f:
            audits = json.load(f)
        
        if len(audits) == 0:
            print_result("Real audit data available", False, "No audits found")
            return False
        
        # Use the most recent audit
        test_audit = audits[0]
        test_audit_id = test_audit.get("audit_id")
        
        print(f"Testing with real audit: {test_audit_id}")
        print(f"Supplier: {test_audit.get('supplier_name')}")
        
        # Step 1: Get report blob
        blob = get_report_blob(test_audit_id)
        
        if not blob:
            print_result("Report blob exists", False, f"No encrypted report for {test_audit_id}")
            return False
        
        print_result("Report blob retrieved", True, f"Supplier: {blob.get('supplier_name')}")
        
        # Step 2: Check payment status
        is_paid = blob.get("paid", False)
        print_result("Payment status", True, f"Paid: {is_paid}")
        
        # Step 3: If not paid, simulate payment
        if not is_paid:
            print("\nSimulating payment...")
            test_tx_id = f"FLOW-TX-{int(time.time())}"
            mark_report_paid(test_audit_id, test_tx_id)
            print_result("Payment marked", True, f"TX: {test_tx_id}")
        
        # Step 4: Try to decrypt
        available, decrypted_text, err = get_decrypted_report(test_audit_id)
        
        print_result("Report decryption", available, 
                    f"Text length: {len(decrypted_text) if decrypted_text else 0} chars")
        
        if available and decrypted_text:
            print(f"\n   Preview: {decrypted_text[:100]}...")
        
        return available
        
    except Exception as e:
        print_result("Report access flow", False, str(e))
        return False


def display_summary(results: dict) -> None:
    """Display final test summary."""
    print_section("TEST SUMMARY")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed} ✓")
    print(f"Failed: {failed} ✗")
    print(f"Success Rate: {(passed/total)*100:.1f}%\n")
    
    for test_name, result in results.items():
        status = "✓" if result else "✗"
        print(f"  {status} {test_name}")
    
    print("\n" + "=" * 70)
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! X402 Revenue System is working correctly.")
    else:
        print(f"⚠️  {failed} test(s) failed. Review the output above for details.")
    print("=" * 70 + "\n")


def main():
    """Run all X402 revenue tests."""
    print("\n" + "=" * 70)
    print("  CfoE X402 Agentic Commerce Revenue System Test Suite")
    print("=" * 70)
    print(f"  Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Project: {PROJECT_ROOT}")
    print("=" * 70)
    
    # Run all tests
    results = {
        "Agent Wallet Initialization": test_agent_wallets(),
        "Encrypted Reports from Audits": test_encrypted_reports_from_audits(),
        "Payment Recording": test_payment_recording(),
        "Revenue Dashboard Aggregation": test_revenue_aggregation(),
        "Report Access Flow": test_report_access_flow(),
    }
    
    # Display summary
    display_summary(results)
    
    # Exit with appropriate code
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
