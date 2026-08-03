from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.pricing import billing_rows, pricing_payload

router = APIRouter()


@router.get("/pricing")
async def pricing():
    return pricing_payload()


def pricing_page() -> HTMLResponse:
    rows = "".join(
        f"<tr><td><code>{escape(row['route'])}</code></td><td>{escape(row['price'])}</td></tr>"
        for row in billing_rows()
    )
    return HTMLResponse(
        "<!doctype html><title>CortexCloud Pricing</title>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<style>body{max-width:900px;margin:3rem auto;padding:0 1rem;font:16px system-ui;color:#e5e7eb;background:#0b1020}"
        "table{width:100%;border-collapse:collapse}td,th{padding:.75rem;border-bottom:1px solid #263248;text-align:left}"
        "code{color:#67e8f9}a{color:#67e8f9}</style>"
        "<h1>CortexCloud pricing</h1><p>Exact x402 charges, generated from the live billing configuration. "
        "<a href='/x402/v1/pricing'>JSON</a></p><table><thead><tr><th>Route</th><th>Price</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
