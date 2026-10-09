# MCP host binding (2026-10-09 fix)

`mcp-bundle.cjs` bound to 127.0.0.1 while the Cloudflare tunnel on ninyi
proxies /mcp* to 192.168.1.15:3100 — every public MCP call 502'd
("connection refused" in cloudflared journal).

Fix: `const HOST = process.env.MCP_HOST || "0.0.0.0";` (was hardcoded
127.0.0.1). nftables already allows :3100 from ninyi only, so the LAN
surface is unchanged; only the tunnel peer can reach it.

Note: the served mcp-bundle.cjs on CT105 is now ahead of git. Commit this
change into cortexcloud-mcp/ when you next sync that repo.
