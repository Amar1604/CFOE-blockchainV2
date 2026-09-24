"""
Quick script to opt-in a recipient account to receive carbon credit tokens.

Usage:
  1. Set RECIPIENT_PRIVATE_KEY below (or convert from mnemonic)
  2. Run: python optin_recipient.py
  3. The script auto-reads the asset ID from data/token_state.json
"""

import json
from pathlib import Path
from algosdk.v2client import algod
from algosdk.transaction import AssetTransferTxn, wait_for_confirmation
from algosdk import account, mnemonic

# Configuration
ALGOD_SERVER = "https://testnet-api.algonode.cloud"
ALGOD_TOKEN = ""

# Auto-load asset ID from persisted state
TOKEN_STATE_FILE = Path(__file__).resolve().parent / "data" / "token_state.json"


def get_asset_id():
    """Load asset ID from token_state.json."""
    if TOKEN_STATE_FILE.exists():
        data = json.loads(TOKEN_STATE_FILE.read_text(encoding="utf-8"))
        asset_id = data.get("carbon_credit_asset_id")
        if asset_id:
            return asset_id
    
    # Fallback: ask user
    return int(input("Enter the Carbon Credit Token Asset ID: ").strip())


def optin_recipient():
    """Opt-in recipient to receive tokens."""
    
    asset_id = get_asset_id()
    
    # Get recipient key — from mnemonic or direct paste
    print("\nHow do you want to provide the recipient's key?")
    print("  1. Paste 25-word mnemonic")
    print("  2. Paste base64 private key")
    choice = input("Choice (1 or 2): ").strip()
    
    if choice == "1":
        words = input("Paste 25-word mnemonic: ").strip()
        recipient_key = mnemonic.to_private_key(words)
    elif choice == "2":
        recipient_key = input("Paste base64 private key: ").strip()
    else:
        print("Invalid choice")
        return
    
    # Connect to Algorand
    algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_SERVER, headers={"User-Agent": "algosdk"})
    
    # Get recipient address from private key
    recipient_address = account.address_from_private_key(recipient_key)
    
    print(f"\nOpting in address: {recipient_address}")
    print(f"Asset ID: {asset_id}")
    
    # Get suggested params
    params = algod_client.suggested_params()
    
    # Create opt-in transaction (0 amount transfer to self)
    txn = AssetTransferTxn(
        sender=recipient_address,
        sp=params,
        receiver=recipient_address,
        amt=0,
        index=asset_id,
    )
    
    # Sign transaction
    signed_txn = txn.sign(recipient_key)
    
    # Send transaction
    tx_id = algod_client.send_transaction(signed_txn)
    print(f"Transaction sent: {tx_id}")
    
    # Wait for confirmation
    result = wait_for_confirmation(algod_client, tx_id, 4)
    print(f"✅ Opt-in successful! Confirmed in round {result['confirmed-round']}")
    print(f"Recipient can now receive tokens at: {recipient_address}")

if __name__ == "__main__":
    optin_recipient()
