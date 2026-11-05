"""Example trading-bot data client using prepaid credits + x402 overages.

Requires: pip install cortexcloud
Environment: CORTEXCLOUD_API_KEY; optional CC_PRIVATE_KEY for x402 overages.
"""
import os
from cortexcloud import CortexCloud

client = CortexCloud(
    api_key=os.environ["CORTEXCLOUD_API_KEY"],
    private_key=os.getenv("CC_PRIVATE_KEY"),
)

wallet = os.environ["TRADING_WALLET"]
chain = os.getenv("CHAIN", "base")

balances = client.token_balances(wallet, chain=chain)
intel = client.wallet_intel(wallet, chain=chain, limit=25)

print("Token balances:", balances["token_count"])
print("Wallet counterparties:", len(intel.get("counterparties", [])))
print("Credits remaining:", client.billing_account()["credits_remaining"])
