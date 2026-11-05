"""Purchase a manual prepaid subscription and print its one-time API key.

Requires: pip install cortexcloud
Environment: CC_PRIVATE_KEY (Base wallet funded with USDC)
"""
import os
from cortexcloud import CortexCloud

private_key = os.environ["CC_PRIVATE_KEY"]
plan = os.getenv("CC_PLAN", "trading-pro")

client = CortexCloud(private_key=private_key)
print("Available plans:")
for item in client.billing_plans()["plans"]:
    print(f"  {item['id']}: ${item['price_usd']:.2f} / month — {item['credits']:,} credits")

purchase = client.subscribe(plan)
print("\nSubscription active:", purchase["plan"])
print("Credits:", purchase["credits_remaining"])
print("Period ends:", purchase["period_end"])
print("\nONE-TIME API KEY (save it securely; it will not be shown again):")
print(purchase["api_key"])
