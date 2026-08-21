"""Domain-specific problem presets: plain-language constraints -> QUBO.

Each builder returns a ProblemInput-compatible dict ({problem_type, n, data})
that can be submitted straight to POST /v1/estimate or /v1/optimize.

ponytail: routing v1 = TSP tour (visit-each-once + one-per-step + distance).
Capacity-constrained VRP needs O(T^3 N^2) penalty terms; add when a customer
asks for it (the generic QUBO path already covers it manually).
"""

from __future__ import annotations

from typing import Any


def portfolio_qubo(returns: list[float], covariance: list[list[float]],
                   cardinality: int | None = None,
                   risk_aversion: float = 1.0,
                   cardinality_penalty: float = 2.0) -> dict[str, Any]:
    """Cardinality-constrained Markowitz.

    minimize -sum(mu_i x_i) + lam*sum_ij(sigma_ij x_i x_j) + gam*(sum x_i - k)^2
    """
    n = len(returns)
    if n < 2:
        raise ValueError("portfolio needs at least 2 assets")
    if cardinality is not None and not (1 <= cardinality <= n):
        raise ValueError(f"cardinality must be in [1, {n}]")
    if len(covariance) != n or any(len(r) != n for r in covariance):
        raise ValueError("covariance must be n x n")
    k = cardinality or max(1, n // 2)
    linear = [-returns[i] + risk_aversion * covariance[i][i] + cardinality_penalty * (1 - 2 * k)
              for i in range(n)]
    quadratic: dict[str, float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            q = 2 * risk_aversion * covariance[i][j] + 2 * cardinality_penalty
            if q != 0.0:
                quadratic[f"{i},{j}"] = q
    return {"problem_type": "qubo", "n": n, "data": {"linear": linear, "quadratic": quadratic}}


def bin_packing_qubo(item_weights: list[float], bin_capacity: float,
                     max_bins: int | None = None) -> dict[str, Any]:
    """Assign every item to exactly one bin, never exceeding capacity,
    minimizing the number of bins used. x[i, b] = item i in bin b.
    """
    n_items = len(item_weights)
    if n_items == 0:
        raise ValueError("need at least 1 item")
    if bin_capacity <= 0:
        raise ValueError("bin_capacity must be positive")
    if max(item_weights) > bin_capacity:
        raise ValueError("an item exceeds bin_capacity")
    B = max_bins or (sum(item_weights) // bin_capacity) + 1
    n = n_items * B

    def idx(i: int, b: int) -> int:
        return i * B + b

    A = 1.0      # assignment penalty (item in exactly one bin)
    P = 1.0      # capacity penalty
    linear = [0.0] * n
    quadratic: dict[str, float] = {}
    for i in range(n_items):
        w = item_weights[i]
        for b in range(B):
            p = idx(i, b)
            linear[p] += -A + P * (w * w - 2 * bin_capacity * w) + 0.25 * b  # bin cost
            for b2 in range(b + 1, B):  # same item in two bins
                quadratic[f"{p},{idx(i, b2)}"] = quadratic.get(f"{p},{idx(i, b2)}", 0.0) + 2 * A
            for i2 in range(i + 1, n_items):  # two items in the same bin
                p2 = idx(i2, b)
                quadratic[f"{p},{p2}"] = quadratic.get(f"{p},{p2}", 0.0) + 2 * P * w * item_weights[i2]
    return {"problem_type": "qubo", "n": n, "data": {"linear": linear, "quadratic": quadratic}}


def routing_qubo(distances: list[list[float]]) -> dict[str, Any]:
    """TSP tour: visit every location exactly once, minimize total distance.
    x[t, i] = location i visited at step t (t wraps around).
    """
    N = len(distances)
    if N < 3:
        raise ValueError("routing needs at least 3 locations")
    if any(len(r) != N for r in distances):
        raise ValueError("distances must be N x N")
    n = N * N

    def idx(t: int, i: int) -> int:
        return t * N + i

    A = 1.0
    linear = [0.0] * n
    quadratic: dict[str, float] = {}
    for i in range(N):                    # each location visited exactly once
        for t in range(N):
            p = idx(t, i)
            linear[p] += -A
            for t2 in range(t + 1, N):
                q = idx(t2, i)
                quadratic[f"{p},{q}"] = quadratic.get(f"{p},{q}", 0.0) + 2 * A
    for t in range(N):                    # one location per step
        for i in range(N):
            p = idx(t, i)
            linear[p] += -A
            for i2 in range(i + 1, N):
                q = idx(t, i2)
                quadratic[f"{p},{q}"] = quadratic.get(f"{p},{q}", 0.0) + 2 * A
    for t in range(N):                    # distance between consecutive steps
        t_next = (t + 1) % N
        for i in range(N):
            for j in range(N):
                if i == j or distances[i][j] == 0.0:
                    continue
                a, b = idx(t, i), idx(t_next, j)
                lo, hi = (a, b) if a < b else (b, a)
                quadratic[f"{lo},{hi}"] = quadratic.get(f"{lo},{hi}", 0.0) + distances[i][j]
    return {"problem_type": "qubo", "n": n, "data": {"linear": linear, "quadratic": quadratic}}


BUILDERS = {
    "portfolio": portfolio_qubo,
    "bin-packing": bin_packing_qubo,
    "routing": routing_qubo,
}
