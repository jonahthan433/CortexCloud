"""Single source of truth for publicly displayed x402 prices."""
from app.x402.pricing import ROUTE_PRICING


def billing_rows() -> list[dict[str, str]]:
    return [
        {"route": route, "price": price}
        for route, price in sorted(ROUTE_PRICING.items())
    ]


def pricing_payload() -> dict[str, object]:
    return {"currency": "USD", "prices": billing_rows()}
