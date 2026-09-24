"""
Quick test script to verify all new features are working.
Run this after starting the webapp to check if features are accessible.
"""

import requests
import json

BASE_URL = "http://localhost:8001"

def test_feature(name, method, endpoint, data=None):
    """Test a single API endpoint"""
    try:
        url = f"{BASE_URL}{endpoint}"
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data)
        
        if response.status_code == 200:
            print(f"✅ {name}: WORKING")
            return response.json()
        else:
            print(f"❌ {name}: FAILED (Status {response.status_code})")
            return None
    except Exception as e:
        print(f"❌ {name}: ERROR - {str(e)}")
        return None

def main():
    print("=" * 60)
    print("🧪 CfoE New Features Test Suite")
    print("=" * 60)
    print()
    
    # Test 1: Leaderboard
    print("📊 Testing Carbon Credits & Leaderboard...")
    leaderboard = test_feature("Leaderboard API", "GET", "/api/leaderboard")
    if leaderboard:
        count = leaderboard.get("count", 0)
        print(f"   → Found {count} suppliers in leaderboard")
        if count > 0:
            top = leaderboard["items"][0]
            print(f"   → Top supplier: {top['supplier_name']} ({top['total_credits']} credits)")
    print()
    
    # Test 2: Credits for specific supplier
    print("💰 Testing Credit Lookup...")
    # Try to get credits for a supplier (will fail if none exist)
    test_feature("Credit Lookup API", "GET", "/api/credits/test_supplier")
    print()
    
    # Test 3: Blockchain Status
    print("⛓️ Testing Blockchain Integration...")
    blockchain = test_feature("Blockchain Status", "GET", "/api/blockchain/status")
    if blockchain:
        print(f"   → Wallet Connected: {blockchain.get('wallet_connected', False)}")
        print(f"   → Network: {blockchain.get('network', 'Unknown')}")
        print(f"   → Token ID: {blockchain.get('token_id', 'Not Created')}")
    print()
    
    # Test 4: Token Summary
    print("🪙 Testing Token System...")
    tokens = test_feature("Token Summary", "GET", "/api/tokens/summary")
    if tokens:
        print(f"   → Asset ID: {tokens.get('asset_id', 'Not Created')}")
        print(f"   → Total Issued: {tokens.get('total_issued', 0)} tons")
        print(f"   → Total Retired: {tokens.get('total_retired', 0)} tons")
    print()
    
    # Test 5: Marketplace
    print("🏪 Testing Marketplace...")
    listings = test_feature("Marketplace Listings", "GET", "/api/marketplace/listings")
    if listings:
        count = listings.get("count", 0)
        print(f"   → Found {count} active listings")
    print()
    
    # Test 6: Compliance Bonds
    print("🔒 Testing Compliance Bonds...")
    bonds = test_feature("Bonds List", "GET", "/api/bonds")
    if bonds:
        count = bonds.get("count", 0)
        print(f"   → Found {count} compliance bonds")
    print()
    
    # Test 7: Submit a test audit
    print("🧪 Testing Audit Submission...")
    audit_data = {
        "supplier_name": "Test Supplier",
        "emissions": 1500,
        "violations": 1,
        "notes": "Test audit from verification script",
        "sector": "default"
    }
    result = test_feature("Audit Submission", "POST", "/api/audit", audit_data)
    if result:
        print(f"   → Audit ID: {result.get('audit_id', 'N/A')}")
        print(f"   → Risk Score: {result.get('risk_score', 0)}")
        credits = result.get('carbon_credits', {})
        if credits:
            print(f"   → Credits Earned: {credits.get('total_credits', 0)}")
            print(f"   → Badges: {credits.get('badges_earned', [])}")
    print()
    
    # Test 8: Check leaderboard again
    print("📊 Re-checking Leaderboard After Audit...")
    leaderboard2 = test_feature("Leaderboard API (After Audit)", "GET", "/api/leaderboard")
    if leaderboard2:
        count = leaderboard2.get("count", 0)
        print(f"   → Now showing {count} suppliers")
    print()
    
    print("=" * 60)
    print("✅ Test Suite Complete!")
    print("=" * 60)
    print()
    print("💡 Next Steps:")
    print("1. Open http://localhost:8001 in your browser")
    print("2. Click the 'Leaderboard' tab to see suppliers")
    print("3. Click 'Carbon Tokens' tab to manage tokens")
    print("4. Submit more audits to see credits accumulate")
    print()

if __name__ == "__main__":
    main()
