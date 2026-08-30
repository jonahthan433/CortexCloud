"""CortexOS Agent — MVP. Phase 1: the policy-controlled x402 wallet.

Reuses cortexcloud.signing.sign_payment for the real EIP-712 signature; this
package only enforces spend policy OUTSIDE the LLM.
"""
