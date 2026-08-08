"""QUBO / Ising problem representations, validation, conversion.

Wire format (agent-friendly JSON):
  {"problem_type": "qubo"|"ising",
   "n": 3,
   "data": {
     "linear": [1.0, 2.0, 3.0],                      # h_i or q_ii
     "quadratic": {"0,1": -2.0, "1,2": 1.5, "0,0": 3.0},  # q_ij (i,j)
   }}

QUBO minimizes E(x) = sum_i q_ii x_i + sum_{i<j} q_ij x_i x_j, x in {0,1}ᵏ.
Ising minimizes H(s) = sum_i h_i s_i + sum_{i<j} J_ij s_i s_j, s in {±1}ⁿ,
convertible via s = 2x − 1 (and the reverse).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_N = 5000  # hard cap at the trust boundary; solvers are smaller
MAX_COEFF = 1e9


class ProblemInput(BaseModel):
    problem_type: str = Field(default="qubo", description="qubo | ising")
    n: int = Field(ge=2, le=MAX_N, description="number of variables")
    data: dict[str, Any] = Field(
        description="{\"linear\": [...], \"quadratic\": {\"i,j\": coeff}}"
    )

    @model_validator(mode="after")
    def _keys_in_range(self) -> "ProblemInput":
        n = self.n
        for key in list((self.data.get("quadratic") or {}).keys()) + list((self.data.get("J") or {}).keys()):
            try:
                i, j = (int(t) for t in key.split(","))
            except (TypeError, ValueError):
                raise ValueError(f"quadratic key must be 'i,j', got {key!r}")
            if not (0 <= i < n and 0 <= j < n):
                raise ValueError(f"quadratic key {key!r} out of range for n={n}")
        return self

    @field_validator("data")
    @classmethod
    def _check_data(cls, v: dict) -> dict:
        if not isinstance(v, dict):
            raise ValueError("data must be an object")
        if "linear" not in v and "quadratic" not in v and "h" not in v and "J" not in v:
            raise ValueError("data needs at least one of linear/quadratic (qubo) or h/J (ising)")
        lin = v.get("linear") or []
        if not isinstance(lin, list) or len(lin) > 1_000_000:
            raise ValueError("linear must be an array of <= 1e6 entries")
        for coeff in lin:
            _check_coeff(coeff)
        for key, coeff in (v.get("quadratic") or {}).items():
            if not isinstance(key, str) or "," not in key:
                raise ValueError(f"quadratic key must be 'i,j', got {key!r}")
            _check_coeff(coeff)
        for key, coeff in (v.get("J") or {}).items():
            if not isinstance(key, str) or "," not in key:
                raise ValueError(f"J key must be 'i,j', got {key!r}")
            _check_coeff(coeff)
        for coeff in (v.get("h") or []):
            _check_coeff(coeff)
        return v


def _check_coeff(v: Any) -> None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"coefficient must be a number, got {v!r}")
    if abs(f) > MAX_COEFF:
        raise ValueError("|coefficient| exceeds 1e9")


def to_qubo(p: ProblemInput) -> dict:
    """Normalized QUBO dict: {"n", "linear": [q_ii...], "quadratic": {"i,j": q_ij}} (i<j)."""
    n = p.n
    linear = [0.0] * n
    quad: dict[str, float] = {}
    for i, v in enumerate(p.data.get("linear") or []):
        if i < n:
            linear[i] = float(v)
    for key, v in (p.data.get("quadratic") or {}).items():
        i, j = (int(t) for t in key.split(","))
        if i == j:
            if i < n:
                linear[i] += float(v)
        else:
            a, b = (i, j) if i < j else (j, i)
            quad[f"{a},{b}"] = quad.get(f"{a},{b}", 0.0) + float(v)
    return {"n": n, "linear": linear, "quadratic": quad}


def qubo_to_ising(qubo: dict, n: int) -> dict:
    """QUBO minimize E(x)=(1/2)xᵀQx -> Ising H(s)=c+sum h_i s_i+sum J_ij s_i s_j, s=2x−1.

    Coefficients: h_i = q_ii/2 + (1/4)Σ_j≠i q_ij ; J_ij = q_ij/4 ; c = Σ_i q_ii/2 + Σ_{i<j} q_ij/4.
    """
    linear = qubo.get("linear") or [0.0] * n
    h = [0.0] * n
    J: dict[str, float] = {}
    const = 0.0
    for i in range(n):
        qii = linear[i] if i < len(linear) else 0.0
        h[i] += qii / 2.0
        const += qii / 2.0
    for key, val in (qubo.get("quadratic") or {}).items():
        i, j = (int(t) for t in key.split(","))
        a, b = (i, j) if i < j else (j, i)
        J[f"{a},{b}"] = J.get(f"{a},{b}", 0.0) + val / 4.0
        h[a] += val / 4.0
        h[b] += val / 4.0
        const += val / 4.0
    return {"n": n, "h": h, "J": J, "const": const}


def ising_energy(h: list[float], J: dict, spins: list[int]) -> float:
    e = sum(hi * s for hi, s in zip(h, spins))
    for key, c in J.items():
        i, j = (int(t) for t in key.split(","))
        if spins[i] and spins[j]:
            e += c
    return e