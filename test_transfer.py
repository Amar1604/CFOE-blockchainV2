"""
Test script for carbon credit transfer functionality
"""

from carbon_token_manager import get_token_manager
from blockchain_client import get_blockchain_client


def test_transfer_functionality():
    """Test transferring carbon credits between addresses."""
    
    print("\n" + "="*70)
    print("  CfoE CARBON CREDIT TRANSFER TEST")
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
    
    # Check initial balance
    balance_info = bc.get_balance()
    print(f"Balance: {balance_info['balance_algo']:.6f} ALGO")
    print(f"Available: {balance_info['available_algo']:.6f} ALGO\n")
    
    # ================================================================== #
    # STEP 1: Create Carbon Credit Token
    # ================================================================== #
    
    print("-"*70)
    print("STEP 1: Creating Carbon Credit Token")
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
    
    print(f"SUCCESS: Carbon Credit Token Created (Asset ID: {asset_id})")
    
    # ================================================================== #
    # STEP 2: Issue Credits to Supplier (for testing transfers)
    # ================================================================== #
    
    print("\n" + "-"*70)
    print("STEP 2: Issuing Credits for Transfer Testing")
    print("-"*70 + "\n")
    
    # Issue credits to self for testing
    recipient = bc.address
    
    tx_id = tm.issue_credits(
        recipient_address=recipient,
        carbon_credits=1000.0,  # 1000 tons CO2eq = 100 CCT tokens
        reason="Initial issuance for transfer testing",
        audit_id="AUD-ISSUE-TEST-001"
    )
    
    if not tx_id:
        print("ERROR: Credit issuance failed")
        return
    
    print(f"SUCCESS: Credits Issued")
    print(f"   Amount: 1,000 tons CO2eq")
    print(f"   Tokens: 100.0 CCT")
    print(f"   TX: {tx_id[:20]}...")
    
    # Check initial token balance after issuance
    token_balance = tm.get_credit_balance(bc.address)
    print(f"\nInitial Token Balance After Issuance:")
    print(f"   Token Balance: {token_balance['tokens']:,.1f} CCT")
    print(f"   Carbon Credits: {token_balance['carbon_credits']:,.0f} tons CO2eq\n")
    
    # ================================================================== #
    # TEST: Transfer Credits
    # ================================================================== #
    
    print("-"*70)
    print("TEST: Transferring Credits")
    print("-"*70 + "\n")
    
    # Transfer 500 tons CO2eq (50 CCT tokens) to self
    transfer_amount = 500.0  # tons CO2eq
    recipient = bc.address  # Self-transfer for testing
    
    tx_id = tm.transfer_credits(
        recipient_address=recipient,
        carbon_credits=transfer_amount,
        reason="Test transfer - validating transfer functionality",
        audit_id="AUD-TRANSFER-TEST-001"
    )
    
    if tx_id:
        print(f"\nTransfer Successful!")
        print(f"   Amount: {transfer_amount} tons CO2eq")
        print(f"   Tokens: {transfer_amount/10:.1f} CCT")
        print(f"   From: {bc.address[:16]}...")
        print(f"   To: {recipient[:16]}...")
        print(f"   TX: {tx_id[:20]}...")
    else:
        print("ERROR: Transfer failed")
        return
    
    # Check balance after transfer
    new_balance = tm.get_credit_balance(bc.address)
    print(f"\nBalance After Transfer:")
    print(f"   Token Balance: {new_balance['tokens']:,.1f} CCT")
    print(f"   Carbon Credits: {new_balance['carbon_credits']:,.0f} tons CO2eq")
    
    # For self-transfer, balance should remain the same
    print(f"\nValidation (Self-transfer):")
    print(f"   Expected Tokens: {token_balance['tokens']:,.1f} CCT")
    print(f"   Actual Tokens:   {new_balance['tokens']:,.1f} CCT")
    print(f"   Match: {abs(token_balance['tokens'] - new_balance['tokens']) < 0.001}")
    
    # Show transaction history
    print(f"\nTransaction History:")
    print(f"   Issued Credits: {len(tm.issued_credits)} transactions")
    print(f"   Retired Credits: {len(tm.retired_credits)} transactions")
    
    print("\n" + "="*70)
    print("  TRANSFER TEST COMPLETED")
    print("="*70 + "\n")


if __name__ == "__main__":
    test_transfer_functionality()