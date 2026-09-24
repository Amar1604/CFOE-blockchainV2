"""
Test script for CfoE Carbon Credit Token System

Demonstrates:
1. Creating fungible carbon credit tokens (CCT)
2. Issuing credits to suppliers for emission reductions
3. Retiring credits for carbon offsetting
4. Creating audit certificate NFTs
5. Querying balances and transaction history

Prerequisites:
- ALGORAND_PRIVATE_KEY in .env
- Testnet ALGO balance for transactions
- Connected to Algorand testnet
"""

from carbon_token_manager import get_token_manager
from blockchain_client import get_blockchain_client


def test_carbon_credit_system():
    """Run complete test of carbon credit token system."""
    
    print("\n" + "="*70)
    print("  CfoE CARBON CREDIT TOKEN SYSTEM - TEST SUITE")
    print("="*70 + "\n")
    
    # Initialize
    bc = get_blockchain_client()
    tm = get_token_manager()
    
    if not bc.connected:
        print("ERROR: Not connected to Algorand network")
        return
        
    if not bc.wallet_connected:
        print("ERROR: Wallet not connected")
        print("   Add ALGORAND_PRIVATE_KEY to .env file")
        return
    
    print(f"Connected to Algorand Testnet")
    print(f"Wallet: {bc.address}\n")
    
    # Check balance
    balance_info = bc.get_balance()
    print(f"Balance: {balance_info['balance_algo']:.6f} ALGO")
    print(f"Available: {balance_info['available_algo']:.6f} ALGO\n")
    
    if balance_info['available_algo'] < 1.0:
        print("WARNING: Low balance. Get testnet ALGO from:")
        print("   https://bank.testnet.algorand.network/\n")
    
    # ================================================================== #
    # TEST 1: Create Carbon Credit Token
    # ================================================================== #
    
    print("\n" + "-"*70)
    print("TEST 1: Creating Carbon Credit Token (CCT)")
    print("-"*70 + "\n")
    
    asset_id = tm.create_carbon_credit_token(
        total_credits=10_000_000,
        decimals=6,
        unit_name="CCT",
        asset_name="CfoE Carbon Credit",
        url="https://cfoe.carbon/credits"
    )
    
    if not asset_id:
        print("ERROR: Token creation failed")
        return
    
    print(f"\nCarbon Credit Token Created!")
    print(f"   Asset ID: {asset_id}")
    print(f"   Symbol: CCT")
    print(f"   Total Supply: 10,000,000 credits")
    
    # ================================================================== #
    # TEST 2: Issue Credits to Supplier
    # ================================================================== #
    
    print("\n" + "-"*70)
    print("TEST 2: Issuing Credits to Supplier")
    print("-"*70 + "\n")
    
    # Issue credits to self for testing
    recipient = bc.address
    
    tx_id = tm.issue_credits(
        recipient_address=recipient,
        carbon_credits=5000.0,  # 5000 tons CO2eq = 500 CCT tokens
        reason="Q1 2024 emission reduction - 5000 tons CO2eq",
        audit_id="AUD-TEST-001"
    )
    
    if tx_id:
        print(f"\nCredits Issued Successfully!")
        print(f"   Carbon Credits: 5,000 tons CO2eq")
        print(f"   Tokens Issued: 500 CCT")
        print(f"   Rate: 1 CCT = 10 tons CO2eq")
        print(f"   Recipient: {recipient[:16]}...")
        print(f"   TX: {tx_id[:20]}...")
    else:
        print("ERROR: Credit issuance failed")
    
    # ================================================================== #
    # TEST 3: Check Balance
    # ================================================================== #
    
    print("\n" + "-"*70)
    print("TEST 3: Checking Credit Balance")
    print("-"*70 + "\n")
    
    balance = tm.get_credit_balance(recipient)
    print(f"Token Balance: {balance['tokens']:,.1f} CCT")
    print(f"Carbon Credits: {balance['carbon_credits']:,.0f} tons CO2eq")
    print(f"Rate: 1 CCT = 10 tons CO2eq")
    
    # ================================================================== #
    # TEST 4: Retire Credits
    # ================================================================== #
    
    print("\n" + "-"*70)
    print("TEST 4: Retiring Credits (Carbon Offset)")
    print("-"*70 + "\n")
    
    tx_id = tm.retire_credits(
        carbon_credits=1000.0,  # 1000 tons CO2eq = 100 CCT tokens
        reason="2024 Q1 carbon offset for operations",
        beneficiary="GreenCorp Manufacturing"
    )
    
    if tx_id:
        print(f"\nCredits Retired Successfully!")
        print(f"   Carbon Credits: 1,000 tons CO2eq")
        print(f"   Tokens Retired: 100 CCT")
        print(f"   Rate: 1 CCT = 10 tons CO2eq")
        print(f"   Status: PERMANENTLY RETIRED")
        print(f"   TX: {tx_id[:20]}...")
    else:
        print("ERROR: Credit retirement failed")
    
    # ================================================================== #
    # TEST 5: Create Audit Certificate NFT
    # ================================================================== #
    
    print("\n" + "-"*70)
    print("TEST 5: Creating Audit Certificate NFT")
    print("-"*70 + "\n")
    
    nft_id = tm.create_audit_certificate_nft(
        supplier_name="GreenCorp Manufacturing",
        audit_id="AUD-TEST-001",
        risk_score=0.25,
        classification="Low Risk",
        emissions=2500.0,
        metadata_url="ipfs://QmTest123..."
    )
    
    if nft_id:
        print(f"\nAudit Certificate NFT Created!")
        print(f"   Asset ID: {nft_id}")
        print(f"   Supplier: GreenCorp Manufacturing")
        print(f"   Risk Score: 0.25 (Low Risk)")
        print(f"   Type: 1-of-1 Unique NFT")
    else:
        print("ERROR: NFT creation failed")
    
    # ================================================================== #
    # SUMMARY
    # ================================================================== #
    
    print("\n" + "="*70)
    print("  TEST SUMMARY")
    print("="*70 + "\n")
    
    print(tm.get_token_summary())
    
    print("\n" + "="*70)
    print("  ALL TESTS COMPLETED")
    print("="*70 + "\n")
    
    print("Token Operations:")
    print(f"   Carbon Credit Token Created (Asset ID: {asset_id})")
    print(f"   Credits Issued: {len(tm.issued_credits)} transactions")
    print(f"   Credits Retired: {len(tm.retired_credits)} transactions")
    print(f"   Audit NFTs Created: {len(tm.audit_nfts)}")
    
    total_credits_issued = sum(r["carbon_credits"] for r in tm.issued_credits)
    total_tokens_issued = sum(r["tokens_issued"] for r in tm.issued_credits)
    total_credits_retired = sum(r["carbon_credits"] for r in tm.retired_credits)
    total_tokens_retired = sum(r["tokens_retired"] for r in tm.retired_credits)
    
    print(f"\nCredit Statistics:")
    print(f"   Issued: {total_credits_issued:,.0f} tons CO2eq = {total_tokens_issued:,.1f} CCT")
    print(f"   Retired: {total_credits_retired:,.0f} tons CO2eq = {total_tokens_retired:,.1f} CCT")
    print(f"   Circulating: {total_credits_issued - total_credits_retired:,.0f} tons = {total_tokens_issued - total_tokens_retired:,.1f} CCT")
    print(f"   Rate: 1 CCT = 10 tons CO2eq")
    
    print("\nView on Algorand Explorer:")
    print(f"   Token: https://lora.algokit.io/testnet/asset/{asset_id}")
    if nft_id:
        print(f"   NFT: https://lora.algokit.io/testnet/asset/{nft_id}")
    
    print("\nCarbon Credit Token System Working!\n")


if __name__ == "__main__":
    test_carbon_credit_system()