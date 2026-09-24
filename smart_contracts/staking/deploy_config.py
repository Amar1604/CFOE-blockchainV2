"""
Deploy config for CCC Staking contract.
"""
import logging
import os

import algokit_utils
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def deploy() -> None:
    algorand  = algokit_utils.AlgorandClient.from_environment()
    deployer  = algorand.account.from_environment("DEPLOYER")
    asset_id  = int(os.getenv("CCC_ASSET_ID", "0"))

    if not asset_id:
        raise ValueError("CCC_ASSET_ID not set — deploy carbon_credit_asa first")

    from smart_contracts.artifacts.staking.staking_client import (
        CCCStakingFactory,
        SetAssetIdArgs,
    )

    factory = algorand.client.get_typed_app_factory(
        CCCStakingFactory, default_sender=deployer.address
    )
    app_client, result = factory.deploy(
        on_update=algokit_utils.OnUpdate.AppendApp,
        on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
    )
    logger.info(f"CCCStaking deployed — App ID: {app_client.app_id}")

    if result.operation_performed in [
        algokit_utils.OperationPerformed.Create,
        algokit_utils.OperationPerformed.Replace,
    ]:
        # Fund treasury with 10 ALGO for yield payouts
        algorand.send.payment(
            algokit_utils.PaymentParams(
                amount=algokit_utils.AlgoAmount(algo=10),
                sender=deployer.address,
                receiver=app_client.app_address,
            )
        )
        logger.info("Funded staking contract with 10 ALGO treasury")

    app_client.send.set_asset_id(args=SetAssetIdArgs(asset_id=asset_id))
    logger.info(f"Asset ID {asset_id} registered in staking contract")
    print(f"\nAdd to .env:\nSTAKING_APP_ID={app_client.app_id}\n")
