"""
Convert Algorand 25-word mnemonic phrase to private key
"""

from algosdk import mnemonic, account

# Paste your 25-word mnemonic phrase here (keep the quotes)
MNEMONIC = ""

# Convert mnemonic to private key
private_key = mnemonic.to_private_key(MNEMONIC)

# Get the address from private key
address = account.address_from_private_key(private_key)

print("=" * 60)
print("ALGORAND WALLET CREDENTIALS")
print("=" * 60)
print(f"\nAddress:\n{address}")
print(f"\nPrivate Key:\n{private_key}")
print("\n" + "=" * 60)
print("\nAdd these to your .env file:")
print("=" * 60)
print(f"ALGORAND_ADDRESS={address}")
print(f"ALGORAND_PRIVATE_KEY={private_key}")
print("=" * 60)
print("\n⚠️  SECURITY WARNING:")
print("   - Delete this script after use")
print("   - Never share your private key")
print("   - Never commit .env to git")
print("=" * 60)
