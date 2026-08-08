"""Quantum backend adapters (provider-neutral)."""

from app.solvers.quantum.base import QuantumBackend
from app.solvers.quantum.braket import BraketBackend, PROVIDERS as BRAKET_PROVIDERS
from app.solvers.quantum.origin import OriginWukongAdapter

__all__ = ["QuantumBackend", "BraketBackend", "BRAKET_PROVIDERS", "OriginWukongAdapter"]