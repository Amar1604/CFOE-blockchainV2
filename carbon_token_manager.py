"""
CfoE Carbon Credit Token System - Algorand ASA Integration

Implements tokenized carbon credits using Algorand Standard Assets (ASA):
1. Fungible Carbon Credits (CCT) - Tradeable emission reduction units
2. Audit Certificate NFTs - Unique proof of compliance for each audit
3. Token Transfer & Trading - P2P carbon credit marketplace
4. Retirement/Burn - Permanent removal of used credits

Usage:
    from carbon_token_manager import get_token_manager
    
    tm = get_token_manager()
    
    # Create carbon credit token pool
    asset_id = tm.create_carbon_credit_token(
        total_credits=10_000_000,
        unit_name="CCT",
        asset_name="CfoE Carbon Credit"
    )
    
    # Issue credits to supplier for emissions reduction
    tm.issue_credits(supplier_address, 5000, "Q1 2024 reduction")
    
    # Create audit certificate NFT
    nft_id = tm.create_audit_certificate_nft(
        supplier_name="GreenCorp",
        audit_id="AUD-12345",
        risk_score=0.25,
        metadata_url="ipfs://..."
    )
"""

import os
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# Persist asset ID so it survives server restarts
_TOKEN_STATE_FILE = Path(__file__).resolve().parent / "data" / "token_state.json"


def _load_persisted_asset_id() -> Optional[int]:
    """Load previously created asset ID from disk."""
    try:
        if _TOKEN_STATE_FILE.exists():
            data = json.loads(_TOKEN_STATE_FILE.read_text(encoding="utf-8"))
            return data.get("carbon_credit_asset_id")
    except Exception:
        pass
    return None


def _save_asset_id(asset_id: int) -> None:
    """Persist asset ID to disk so it survives restarts."""
    try:
        _TOKEN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if _TOKEN_STATE_FILE.exists():
            try:
                existing = json.loads(_TOKEN_STATE_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        existing["carbon_credit_asset_id"] = asset_id
        _TOKEN_STATE_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  [Token] WARNING: Could not persist asset ID: {e}")


_LEDGER_FILE = Path(__file__).resolve().parent / "data" / "credit_issuance_ledger.json"
_RETIRED_FILE = Path(__file__).resolve().parent / "data" / "retired_credits_ledger.json"


def _load_persisted_ledger() -> List[Dict]:
    """Load previously issued credits from disk."""
    try:
        if _LEDGER_FILE.exists():
            content = _LEDGER_FILE.read_text(encoding="utf-8").strip()
            if content:
                return json.loads(content)
    except Exception as e:
        print(f"  [Token] WARNING: Could not load ledger: {e}")
    return []


def _load_persisted_retired() -> List[Dict]:
    """Load previously retired credits from disk."""
    try:
        if _RETIRED_FILE.exists():
            content = _RETIRED_FILE.read_text(encoding="utf-8").strip()
            if content:
                return json.loads(content)
    except Exception as e:
        print(f"  [Token] WARNING: Could not load retired ledger: {e}")
    return []


def _save_ledger(issued_credits: List[Dict]) -> None:
    """Persist the issued credits ledger to disk."""
    try:
        _LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LEDGER_FILE.write_text(json.dumps(issued_credits, indent=2), encoding="utf-8")
        print(f"  [Token] Saved {len(issued_credits)} issued records to ledger")
    except Exception as e:
        print(f"  [Token] WARNING: Could not persist ledger: {e}")


def _save_retired(retired_credits: List[Dict]) -> None:
    """Persist the retired credits ledger to disk."""
    try:
        _RETIRED_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RETIRED_FILE.write_text(json.dumps(retired_credits, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  [Token] WARNING: Could not persist retired ledger: {e}")


class CarbonCreditTokenManager:
    """
    Manages tokenized carbon credits and audit certificates on Algorand.
    
    Token Economics:
    - 1 CCT Token = 10 Carbon Credits (tons CO2eq)
    - Example: 5000 tons CO2eq reduction = 500 CCT tokens
    - Fractional tokens supported (0.1 CCT = 1 ton CO2eq)
    
    Features:
    - Fungible carbon credit tokens (ASA) for trading emission reductions
    - NFT audit certificates for compliance proof
    - Credit issuance, transfer, and retirement
    - Integration with CfoE audit pipeline
    """
    
    # Token conversion rate: 1 token = 10 carbon credits (tons CO2eq)
    CREDITS_PER_TOKEN = 10
    
    def __init__(self, blockchain_client):
        self.bc = blockchain_client
        # Load persisted asset ID — survives server restarts
        self.carbon_credit_asset_id = _load_persisted_asset_id()
        if self.carbon_credit_asset_id:
            print(f"  [Token] Loaded persisted asset ID: {self.carbon_credit_asset_id}")
        self.issued_credits: List[Dict] = _load_persisted_ledger()
        if self.issued_credits:
            print(f"  [Token] Loaded {len(self.issued_credits)} persisted credit records")
        self.retired_credits: List[Dict] = _load_persisted_retired()
        if self.retired_credits:
            print(f"  [Token] Loaded {len(self.retired_credits)} persisted retired records")
        self.audit_nfts: List[Dict] = []
        
    # ================================================================== #
    #  CARBON CREDIT TOKEN CREATION
    # ================================================================== #
    
    def create_carbon_credit_token(
        self,
        total_credits: int = 10_000_000,
        decimals: int = 1,
        unit_name: str = "CCT",
        asset_name: str = "CfoE Carbon Credit",
        url: str = "https://cfoe.carbon/credits",
    ) -> Optional[int]:
        """
        Create a fungible carbon credit token (ASA).
        
        Token Economics:
        - 1 CCT Token = 10 Carbon Credits (tons CO2eq)
        - Total supply in tokens = total_credits / 10
        - Example: 10M credits = 1M tokens
        - 1 decimal place allows 0.1 CCT = 1 ton CO2eq
        
        Args:
            total_credits: Total carbon credits in tons CO2eq (default 10M)
            decimals: Decimal places (default 1 for 0.1 precision)
            unit_name: Short ticker symbol (default "CCT")
            asset_name: Full name of the asset
            url: URL with token information
            
        Returns:
            Asset ID of the created token, or None if failed
        """
        if not self.bc.connected or not self.bc.wallet_connected:
            print("  [Token] ERROR: Wallet not connected")
            return None
            
        try:
            from algosdk.transaction import AssetConfigTxn, wait_for_confirmation
            
            params = self.bc.algod_client.suggested_params()
            
            # Calculate total tokens: 1 token = 10 credits
            total_tokens = total_credits // self.CREDITS_PER_TOKEN
            
            # Create asset configuration transaction
            txn = AssetConfigTxn(
                sender=self.bc.address,
                sp=params,
                total=total_tokens * (10 ** decimals),  # Total with decimals
                default_frozen=False,
                unit_name=unit_name,
                asset_name=asset_name,
                manager=self.bc.address,
                reserve=self.bc.address,
                freeze=self.bc.address,
                clawback=self.bc.address,
                url=url,
                decimals=decimals,
            )
            
            env_key = os.getenv("ALGORAND_PRIVATE_KEY")
            if not env_key:
                print("  [Token] ERROR: ALGORAND_PRIVATE_KEY required for token creation")
                return None
                
            signed_txn = txn.sign(env_key)
            tx_id = self.bc.algod_client.send_transaction(signed_txn)
            
            result = wait_for_confirmation(self.bc.algod_client, tx_id, 4)
            asset_id = result["asset-index"]
            
            self.carbon_credit_asset_id = asset_id
            _save_asset_id(asset_id)  # Persist so it survives server restarts
            
            print(f"  [Token] CARBON CREDIT TOKEN CREATED")
            print(f"          Asset ID:       {asset_id}")
            print(f"          Name:           {asset_name}")
            print(f"          Symbol:         {unit_name}")
            print(f"          Total Tokens:   {total_tokens:,} CCT")
            print(f"          Total Credits:  {total_credits:,} tons CO2eq")
            print(f"          Rate:           1 CCT = {self.CREDITS_PER_TOKEN} tons CO2eq")
            print(f"          Decimals:       {decimals}")
            print(f"          TX:             {tx_id}")
            
            return asset_id
            
        except Exception as e:
            print(f"  [Token] ERROR creating carbon credit token: {e}")
            return None
    
    # ================================================================== #
    #  ASSET OPT-IN
    # ================================================================== #
    
    def optin_to_asset(self, asset_id: int, recipient_key: str = None) -> Optional[str]:
        """
        Opt-in to an asset to be able to receive it.
        
        Args:
            asset_id: The asset ID to opt-in to
            recipient_key: Optional private key for opting in another account
            
        Returns:
            Transaction ID or None if failed
        """
        if not self.bc.connected:
            print("  [Token] ERROR: Blockchain not connected")
            return None
            
        # Use provided key or default to wallet key
        signing_key = recipient_key or os.getenv("ALGORAND_PRIVATE_KEY")
        if not signing_key:
            print("  [Token] ERROR: No private key available")
            return None
            
        try:
            from algosdk.transaction import AssetTransferTxn, wait_for_confirmation
            from algosdk import account
            
            # Get address from key
            sender_address = account.address_from_private_key(signing_key)
            
            params = self.bc.algod_client.suggested_params()
            
            # Opt-in is a 0-amount transfer to self
            txn = AssetTransferTxn(
                sender=sender_address,
                sp=params,
                receiver=sender_address,
                amt=0,
                index=asset_id,
            )
            
            signed_txn = txn.sign(signing_key)
            tx_id = self.bc.algod_client.send_transaction(signed_txn)
            
            wait_for_confirmation(self.bc.algod_client, tx_id, 4)
            
            print(f"  [Token] OPTED IN to asset {asset_id}")
            print(f"          Address: {sender_address}")
            print(f"          TX: {tx_id}")
            
            return tx_id
            
        except Exception as e:
            print(f"  [Token] ERROR opting in: {e}")
            return None
    
    # ================================================================== #
    #  CREDIT ISSUANCE
    # ================================================================== #
    
    def issue_credits(
        self,
        recipient_address: str,
        carbon_credits: float,
        reason: str,
        audit_id: Optional[str] = None,
    ) -> Optional[str]:
        """Issue carbon credits to a supplier."""
        if not self.carbon_credit_asset_id:
            print("  [Token] ERROR: Carbon credit token not created yet")
            return None
            
        if not self.bc.connected or not self.bc.wallet_connected:
            print("  [Token] ERROR: Wallet not connected")
            return None
        
        tokens = carbon_credits / self.CREDITS_PER_TOKEN
        print(f"  [Token] Attempting to issue {carbon_credits} credits to {recipient_address}")
        
        tx_id = self._try_asa_transfer(recipient_address, carbon_credits, tokens, reason, audit_id, "CfoE_CREDIT_ISSUANCE")
        
        if tx_id:
            record = {
                "recipient": recipient_address,
                "issuer_address": self.bc.address,
                "carbon_credits": carbon_credits,
                "tokens_issued": tokens,
                "reason": reason,
                "audit_id": audit_id,
                "tx_id": tx_id,
                "method": "asa_transfer",
                "timestamp": datetime.now().isoformat(),
            }
            self.issued_credits.append(record)
            _save_ledger(self.issued_credits)
            
            print(f"  [Token] CREDITS ISSUED (ASA Transfer)")
            print(f"          Recipient:      {recipient_address[:16]}...")
            print(f"          Carbon Credits: {carbon_credits:,.0f} tons CO2eq")
            print(f"          Tokens Issued:  {tokens:,.1f} CCT")
            print(f"          TX:             {tx_id}")
            return tx_id
        
        print(f"  [Token] ASA transfer unavailable, recording via on-chain note transaction")
        result = self.issue_credits_via_note(recipient_address, carbon_credits, reason, audit_id)
        if result:
            return result.get("tx_id") or result.get("local_id")
        return None
    
    def _try_asa_transfer(self, recipient: str, credits: float, tokens: float, reason: str, audit_id: str, tx_type: str) -> Optional[str]:
        """Attempt a real ASA token transfer. Returns tx_id or None."""
        try:
            from algosdk.transaction import AssetTransferTxn, wait_for_confirmation
            
            params = self.bc.algod_client.suggested_params()
            amount_micro = int(tokens * 10)
            
            txn = AssetTransferTxn(
                sender=self.bc.address,
                sp=params,
                receiver=recipient,
                amt=amount_micro,
                index=self.carbon_credit_asset_id,
                note=json.dumps({
                    "type": tx_type,
                    "carbon_credits": credits,
                    "tokens": tokens,
                    "reason": reason,
                    "audit_id": audit_id or "N/A",
                    "timestamp": datetime.now().isoformat(),
                }).encode('utf-8')
            )
            
            env_key = os.getenv("ALGORAND_PRIVATE_KEY")
            if not env_key:
                return None
                
            signed_txn = txn.sign(env_key)
            tx_id = self.bc.algod_client.send_transaction(signed_txn)
            wait_for_confirmation(self.bc.algod_client, tx_id, 4)
            return tx_id
            
        except Exception as e:
            print(f"  [Token] ASA transfer skipped: {str(e)[:80]}")
            return None
    
    def issue_credits_via_note(
        self,
        recipient_address: str,
        carbon_credits: float,
        reason: str,
        audit_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Record a credit issuance on-chain using a note transaction.
        
        This bypasses the ASA opt-in requirement by recording the issuance
        as a 0-ALGO self-payment with the transfer data in the note field.
        The blockchain still has an immutable, verifiable record.
        """
        if not self.bc.connected or not self.bc.wallet_connected:
            print("  [Token] ERROR: Wallet not connected")
            return None
        
        tokens = carbon_credits / self.CREDITS_PER_TOKEN
        timestamp = datetime.now().isoformat()
        
        note_data = {
            "type": "CfoE_CREDIT_ISSUANCE",
            "version": "2.0",
            "asset_id": self.carbon_credit_asset_id,
            "recipient": recipient_address,
            "carbon_credits": carbon_credits,
            "tokens_issued": tokens,
            "reason": reason,
            "audit_id": audit_id or "N/A",
            "issuer_address": self.bc.address,
            "timestamp": timestamp,
        }
        
        tx_id = self.bc._send_note_tx(note_data)
        on_chain = tx_id is not None
        
        record = {
            "recipient": recipient_address,
            "carbon_credits": carbon_credits,
            "tokens_issued": tokens,
            "reason": reason,
            "audit_id": audit_id,
            "tx_id": tx_id,
            "local_id": f"ISSUE-{int(datetime.now().timestamp())}" if not tx_id else None,
            "method": "note_transaction",
            "on_chain": on_chain,
            "timestamp": timestamp,
        }
        self.issued_credits.append(record)
        _save_ledger(self.issued_credits)
        
        status = "ON-CHAIN" if on_chain else "LOCAL"
        tx_display = tx_id or record["local_id"]
        print(f"  [Token] CREDITS ISSUED ({status} note-tx)")
        print(f"          Recipient:      {recipient_address}")
        print(f"          Carbon Credits: {carbon_credits:,.0f} tons CO2eq")
        print(f"          Tokens Issued:  {tokens:,.1f} CCT")
        print(f"          Reason:         {reason}")
        print(f"          Audit:          {audit_id or 'N/A'}")
        print(f"          TX:             {tx_display}")
        
        return record
    
    # ================================================================== #
    #  CREDIT TRANSFER
    # ================================================================== #

    def transfer_credits(
        self,
        recipient_address: str,
        carbon_credits: float,
        reason: str,
        audit_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Transfer carbon credit tokens to another address.
        
        Token Economics:
        - Input: carbon_credits in tons CO2eq
        - Tokens transferred: carbon_credits / 10
        - Example: 1000 tons CO2eq = 100 CCT tokens transferred
        
        Args:
            recipient_address: Algorand address to receive tokens
            carbon_credits: Carbon credits in tons CO2eq to transfer
            reason: Reason for transfer
            audit_id: Associated audit ID for traceability
            
        Returns:
            Transaction ID or None if failed
        """
        if not self.carbon_credit_asset_id:
            print("  [Token] ERROR: Carbon credit token not created yet. Create one first via POST /api/tokens/create")
            return None
            
        if not self.bc.connected or not self.bc.wallet_connected:
            print("  [Token] ERROR: Wallet not connected")
            return None

        tokens = carbon_credits / self.CREDITS_PER_TOKEN
        
        # Try real ASA transfer first
        tx_id = self._try_asa_transfer(recipient_address, carbon_credits, tokens, reason, audit_id, "CfoE_CREDIT_TRANSFER")
        
        if tx_id:
            record = {
                "recipient": recipient_address,
                "sender": self.bc.address,
                "carbon_credits": carbon_credits,
                "tokens_transferred": tokens,
                "reason": reason,
                "audit_id": audit_id,
                "tx_id": tx_id,
                "method": "asa_transfer",
                "timestamp": datetime.now().isoformat(),
            }
            
            print(f"  [Token] CREDITS TRANSFERRED (ASA Transfer)")
            print(f"          From:           {self.bc.address[:16]}...")
            print(f"          To:             {recipient_address[:16]}...")
            print(f"          Carbon Credits: {carbon_credits:,.0f} tons CO2eq")
            print(f"          Tokens:         {tokens:,.1f} CCT")
            print(f"          TX:             {tx_id}")
            
            return tx_id
        
        # ASA transfer unavailable — record via note transaction instead
        print(f"  [Token] ASA transfer unavailable, recording transfer via on-chain note")
        result = self.issue_credits_via_note(recipient_address, carbon_credits, reason, audit_id)
        if result:
            return result.get("tx_id") or result.get("local_id")
        return None


    # ================================================================== #
    #  CREDIT RETIREMENT (BURN)
    # ================================================================== #
    
    def retire_credits(
        self,
        carbon_credits: float,
        reason: str,
        beneficiary: str,
    ) -> Optional[str]:
        """
        Permanently retire (burn) carbon credits by sending to creator (reserve).
        
        Token Economics:
        - Input: carbon_credits in tons CO2eq
        - Tokens retired: carbon_credits / 10
        - Example: 1000 tons CO2eq = 100 CCT tokens retired
        - Tokens are sent back to reserve and marked as retired
        
        Args:
            carbon_credits: Carbon credits to retire in tons CO2eq
            reason: Reason for retirement
            beneficiary: Company/entity benefiting from the offset
            
        Returns:
            Transaction ID or None if failed
        """
        if not self.carbon_credit_asset_id:
            print("  [Token] ERROR: Carbon credit token not created yet")
            return None
            
        if not self.bc.connected or not self.bc.wallet_connected:
            print("  [Token] ERROR: Wallet not connected")
            return None
            
        try:
            from algosdk.transaction import AssetTransferTxn, wait_for_confirmation
            
            # Send tokens back to reserve (creator address) to retire them
            reserve_address = self.bc.address
            params = self.bc.algod_client.suggested_params()
            
            # Convert carbon credits to tokens
            tokens = carbon_credits / self.CREDITS_PER_TOKEN
            amount_micro = int(tokens * 10)
            
            # Check if user has enough balance
            balance_info = self.get_credit_balance(self.bc.address)
            if balance_info["tokens"] < tokens:
                print(f"  [Token] ERROR: Insufficient balance. Have {balance_info['tokens']:.1f} CCT, need {tokens:.1f} CCT")
                return None
            
            txn = AssetTransferTxn(
                sender=self.bc.address,
                sp=params,
                receiver=reserve_address,  # Send to reserve to retire
                amt=amount_micro,
                index=self.carbon_credit_asset_id,
                note=json.dumps({
                    "type": "CfoE_CREDIT_RETIREMENT",
                    "carbon_credits": carbon_credits,
                    "tokens_retired": tokens,
                    "reason": reason,
                    "beneficiary": beneficiary,
                    "timestamp": datetime.now().isoformat(),
                    "status": "PERMANENTLY_RETIRED",
                }).encode('utf-8')
            )
            
            env_key = os.getenv("ALGORAND_PRIVATE_KEY")
            if not env_key:
                print("  [Token] ERROR: ALGORAND_PRIVATE_KEY required")
                return None
                
            signed_txn = txn.sign(env_key)
            tx_id = self.bc.algod_client.send_transaction(signed_txn)
            
            wait_for_confirmation(self.bc.algod_client, tx_id, 4)
            
            record = {
                "sender": self.bc.address,
                "carbon_credits": carbon_credits,
                "tokens_retired": tokens,
                "reason": reason,
                "beneficiary": beneficiary,
                "tx_id": tx_id,
                "timestamp": datetime.now().isoformat(),
                "status": "RETIRED",
            }
            self.retired_credits.append(record)
            _save_retired(self.retired_credits)
            
            print(f"  [Token] CREDITS RETIRED")
            print(f"          Carbon Credits: {carbon_credits:,.0f} tons CO2eq")
            print(f"          Tokens Retired: {tokens:,.1f} CCT")
            print(f"          Rate:           1 CCT = {self.CREDITS_PER_TOKEN} tons")
            print(f"          Beneficiary:    {beneficiary}")
            print(f"          Reason:         {reason}")
            print(f"          TX:             {tx_id}")
            print(f"          Status:         PERMANENTLY RETIRED")
            
            return tx_id
            
        except Exception as e:
            print(f"  [Token] ERROR retiring credits: {e}")
            return None
    
    # ================================================================== #
    #  AUDIT CERTIFICATE NFT
    # ================================================================== #
    
    def create_audit_certificate_nft(
        self,
        supplier_name: str,
        audit_id: str,
        risk_score: float,
        classification: str,
        emissions: float,
        metadata_url: str = "",
    ) -> Optional[int]:
        """
        Create a unique NFT certificate for a completed audit.
        
        Each audit gets a 1-of-1 NFT that proves compliance and can be
        displayed/verified. The NFT contains audit metadata and links to
        the full on-chain audit trail.
        
        Args:
            supplier_name: Name of audited supplier
            audit_id: Unique audit identifier
            risk_score: ESG risk score
            classification: Risk classification
            emissions: CO2 emissions audited
            metadata_url: IPFS/URL with full audit metadata
            
        Returns:
            Asset ID of the NFT, or None if failed
        """
        if not self.bc.connected or not self.bc.wallet_connected:
            print("  [Token] ERROR: Wallet not connected")
            return None
            
        try:
            from algosdk.transaction import AssetConfigTxn, wait_for_confirmation
            
            params = self.bc.algod_client.suggested_params()
            
            # Create metadata hash
            metadata = {
                "supplier": supplier_name,
                "audit_id": audit_id,
                "risk_score": risk_score,
                "classification": classification,
                "emissions": emissions,
                "timestamp": datetime.now().isoformat(),
            }
            metadata_hash = hashlib.sha256(
                json.dumps(metadata).encode('utf-8')
            ).digest()[:32]  # 32 bytes for Algorand
            
            # NFT configuration (total=1, decimals=0)
            txn = AssetConfigTxn(
                sender=self.bc.address,
                sp=params,
                total=1,  # Only 1 NFT
                decimals=0,  # No fractional NFTs
                default_frozen=False,
                unit_name="CFOE",
                asset_name=f"CfoE Audit: {supplier_name[:20]}",
                manager=self.bc.address,
                reserve=self.bc.address,
                freeze=self.bc.address,
                clawback=self.bc.address,
                url=metadata_url or f"https://cfoe.carbon/audit/{audit_id}",
                metadata_hash=metadata_hash,
            )
            
            env_key = os.getenv("ALGORAND_PRIVATE_KEY")
            if not env_key:
                print("  [Token] ERROR: ALGORAND_PRIVATE_KEY required")
                return None
                
            signed_txn = txn.sign(env_key)
            tx_id = self.bc.algod_client.send_transaction(signed_txn)
            
            result = wait_for_confirmation(self.bc.algod_client, tx_id, 4)
            asset_id = result["asset-index"]
            
            record = {
                "asset_id": asset_id,
                "supplier_name": supplier_name,
                "audit_id": audit_id,
                "risk_score": risk_score,
                "classification": classification,
                "emissions": emissions,
                "metadata_url": metadata_url,
                "tx_id": tx_id,
                "timestamp": datetime.now().isoformat(),
            }
            self.audit_nfts.append(record)
            
            print(f"  [Token] AUDIT CERTIFICATE NFT CREATED")
            print(f"          Asset ID:       {asset_id}")
            print(f"          Supplier:       {supplier_name}")
            print(f"          Audit ID:       {audit_id}")
            print(f"          Risk Score:     {risk_score:.2f} ({classification})")
            print(f"          Emissions:      {emissions:,.0f} tons CO2")
            print(f"          TX:             {tx_id}")
            
            return asset_id
            
        except Exception as e:
            print(f"  [Token] ERROR creating audit NFT: {e}")
            return None
    
    # ================================================================== #
    #  QUERY & STATUS
    # ================================================================== #
    
    def get_credit_balance(self, address: str) -> Dict[str, Any]:
        """Get carbon credit balance for an address.
        
        Combines two sources:
        1. On-chain ASA holdings (real token transfers)
        2. Note-transaction-based issuances from the internal ledger
        
        Returns:
            Dict with tokens, carbon_credits, and opted_in status
        """
        asa_tokens = 0.0
        opted_in = False
        
        # 1. Check on-chain ASA balance
        if self.carbon_credit_asset_id and self.bc.connected:
            try:
                account_info = self.bc.algod_client.account_info(address)
                assets = account_info.get("assets", [])
                
                for asset in assets:
                    if asset["asset-id"] == self.carbon_credit_asset_id:
                        asa_tokens = asset["amount"] / 10  # Convert from micro (1 decimal)
                        opted_in = True
                        break
            except Exception as e:
                print(f"  [Token] ERROR getting on-chain balance: {e}")
        
        # 2. Sum note-transaction-based credits issued to this address
        ledger_tokens = 0.0
        for record in self.issued_credits:
            if record.get("recipient") == address and record.get("method") == "note_transaction":
                ledger_tokens += record.get("tokens_issued", 0.0)
        
        total_tokens = asa_tokens + ledger_tokens
        total_credits = total_tokens * self.CREDITS_PER_TOKEN
        
        # Consider the address "opted in" if they have any balance (ASA or ledger)
        effective_opted_in = opted_in or ledger_tokens > 0
        
        return {
            "tokens": total_tokens,
            "carbon_credits": total_credits,
            "opted_in": effective_opted_in,
            "asa_tokens": asa_tokens,
            "ledger_tokens": ledger_tokens,
        }
    
    def get_token_summary(self) -> str:
        """Get formatted summary of token operations."""
        lines = []
        lines.append("=" * 60)
        lines.append("  CARBON CREDIT TOKEN SUMMARY")
        lines.append("=" * 60)
        
        if self.carbon_credit_asset_id:
            lines.append(f"  Carbon Credit Asset ID: {self.carbon_credit_asset_id}")
            lines.append(f"  Total Issued:           {len(self.issued_credits)} transactions")
            lines.append(f"  Total Retired:          {len(self.retired_credits)} transactions")
            lines.append(f"  Audit NFTs Created:     {len(self.audit_nfts)}")
        else:
            lines.append("  No carbon credit token created yet")
            
        if self.issued_credits:
            total_credits = sum(r["carbon_credits"] for r in self.issued_credits)
            total_tokens = sum(r["tokens_issued"] for r in self.issued_credits)
            lines.append(f"\n  Credits Issued:         {total_credits:,.0f} tons CO2eq")
            lines.append(f"  Tokens Issued:          {total_tokens:,.1f} CCT")
            
        if self.retired_credits:
            total_credits = sum(r["carbon_credits"] for r in self.retired_credits)
            total_tokens = sum(r["tokens_retired"] for r in self.retired_credits)
            lines.append(f"  Credits Retired:        {total_credits:,.0f} tons CO2eq")
            lines.append(f"  Tokens Retired:         {total_tokens:,.1f} CCT")
            
        lines.append("=" * 60)
        return "\n".join(lines)

    def refresh_ledgers(self) -> None:
        """Reload ledgers from disk."""
        self.issued_credits = _load_persisted_ledger()
        self.retired_credits = _load_persisted_retired()


# ================================================================== #
#  SINGLETON
# ================================================================== #

_token_manager_instance = None


def get_token_manager():
    """Get or create the singleton token manager."""
    global _token_manager_instance
    if _token_manager_instance is None:
        from blockchain_client import get_blockchain_client
        bc = get_blockchain_client()
        _token_manager_instance = CarbonCreditTokenManager(bc)
    return _token_manager_instance
