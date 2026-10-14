"""Regenerate openapi.json from the live app (no static drift).

Run on the server: python scripts/gen_openapi.py
Serves the freshly-generated spec instead of a hand-maintained file, so
openapi.json can never drift from the mounted routes again.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import create_app  # noqa: E402

app = create_app(override_openapi=False)
spec = app.openapi()

out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.json")
with open(out, "w") as f:
    json.dump(spec, f, indent=2, ensure_ascii=False)

print(f"wrote {out}: {len(spec['paths'])} paths")
