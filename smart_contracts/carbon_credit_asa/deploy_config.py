"""
Deploy config for the CCC ASA Manager contract.
Runs via: python -m smart_contracts carbon_credit_asa deploy
"""

import logging
import os

import algokit_utils
from algosdk import account as algo_account
from algosdk.transaction import AssetConfigTxn, wait_for_confirmation
from algosdk.v2client import algod
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def deploy() -> None:
    """
    1. Create the CCC ASA (decimals=0, total=0 minting model)
    2. Deploy the CarbonCreditASA manager contract
    3. Call set_asset_id on the contract to register the ASA
    """
    algorand = algokit_utils.AlgorandClient.from_environment()
    deployer = algorand.account.from_environment("DEPLOYER")

    # ── Step 1: Create the CCC ASA ──────────────────────────────────────
    private_key = os.getenv("ALGORAND_PRIVATE_KEY")
    if not private_key:
        raise ValueError("ALGORAND_PRIVATE_KEY not set in environment")

    algod_server = os.getenv("ALGOD_SERVER", "https://testnet-api.algonode.cloud")
    algod_token  = os.getenv("ALGOD_TOKEN", "")
    algod_client = algod.AlgodClient(
        algod_token, algod_server,
        headers={"User-Agent": "algosdk"} if not algod_token else {}
    )

    auditor_address = algo_account.address_from_private_key(private_key)
    params = algod_client.suggested_params()

    asa_txn = AssetConfigTxn(
        sender=auditor_address,
        sp=params,
        total=0,                       # Pure-minting: supply starts at 0
        default_frozen=False,
        unit_name="CCC",
        asset_name="CfoE Carbon Credit",
        manager=auditor_address,       # Can modify / mint
        reserve=auditor_address,       # Reserve account
        freeze=auditor_address,        # Can freeze
        clawback=auditor_address,      # Enables slashing
        url="https://cfoe.carbon/ccc",
        decimals=0,                    # Whole credits only
        note=b"CfoE Carbon Credit - ESG compliance token",
    )

    signed_asa = asa_txn.sign(private_key)
    asa_tx_id  = algod_client.send_transaction(signed_asa)
    asa_result = wait_for_confirmation(algod_client, asa_tx_id, 4)
    asset_id   = asa_result["asset-index"]

    logger.info(f"CCC ASA created — Asset ID: {asset_id}, TX: {asa_tx_id}")

    # ── Step 2: Deploy CarbonCreditASA contract ────────────────────────
    from smart_contracts.artifacts.carbon_credit_asa.carbon_credit_asa_client import (
        CarbonCreditASAFactory,
        SetAssetIdArgs,
    )

    factory = algorand.client.get_typed_app_factory(
        CarbonCreditASAFactory, default_sender=deployer.address
    )
    app_client, result = factory.deploy(
        on_update=algokit_utils.OnUpdate.AppendApp,
        on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
    )
    logger.info(f"CarbonCreditASA deployed — App ID: {app_client.app_id}")

    # Fund contract for box MBR
    if result.operation_performed in [
        algokit_utils.OperationPerformed.Create,
        algokit_utils.OperationPerformed.Replace,
    ]:
        algorand.send.payment(
            algokit_utils.PaymentParams(
                amount=algokit_utils.AlgoAmount(algo=2),
                sender=deployer.address,
                receiver=app_client.app_address,
            )
        )

    # ── Step 3: Register asset_id in contract ─────────────────────────
    app_client.send.set_asset_id(args=SetAssetIdArgs(asset_id=asset_id))
    logger.info(f"Asset ID {asset_id} registered in contract")

    # Persist to .env for the Python layer to read
    print(f"\nAdd to .env:\nCCC_ASSET_ID={asset_id}\nCCC_APP_ID={app_client.app_id}\n")
