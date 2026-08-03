"""Run directly: no pytest fixture, no production DB writes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.x402.pricing import ROUTE_PRICING
from app.pricing import billing_rows
from app.x402.bazaar_routes import mcp_tools


def main() -> None:
    assert settings.X402_RESOURCE_BASE == "https://api.cortexcloud.org"
    rows = {row["route"]: row["price"] for row in billing_rows()}
    assert rows == ROUTE_PRICING
    tools = {tool["name"]: tool for tool in mcp_tools()}
    assert {"chat_completions", "embeddings", "image_generation", "image_edit", "text_to_speech", "transcription", "base_balance"} <= tools.keys()
    assert tools["chat_completions"]["_route"] == ("POST", "/x402/v1/chat/completions")
    assert tools["base_balance"]["_route"] == ("GET", "/x402/v1/data/base/balance")


if __name__ == "__main__":
    main()
