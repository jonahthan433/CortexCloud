"""
CortexCloud Optimization Network — solver adapters.

Agent-facing API never imports a specific backend; it talks to this
package through the Solver protocol in `base.py`. Quantum/hardware
providers live inside `origin.py` and are only loadable when their
credentials are configured — the public surface has zero knowledge of
any quantum provider.
"""