"""Seeded, undirected graph models for independent peer groups."""

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType

import networkx as nx


@dataclass(frozen=True)
class Group:
    """A generated group's resolved model parameters, seed, and ordered peer IDs."""

    id: str
    domain: str
    seed: int
    params: Mapping[str, int | float]
    members: tuple[str, ...]


class _GroupError(ValueError):
    def __init__(self, field: tuple[str, ...], detail: str):
        self.field = field
        super().__init__(detail)


def _integer(value, *field):
    if isinstance(value, bool) or not isinstance(value, int):
        raise _GroupError(field, f"{field[-1]} must be an integer")
    return value


def _probability(value, field):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 1:
        raise _GroupError(("params", field), f"{field} must be a probability from 0 to 1")
    return value


def _generate(group_id: str, n: int, domain: str, params: Mapping,
              seed: int | None, master_seed: int):
    _integer(n, "n")
    if n < 1:
        raise _GroupError(("n",), "n must be at least 1")
    fields = {"er": ("p",), "ws": ("k", "beta"), "ba": ("m",), "ring": (), "mesh": ()}
    if not isinstance(domain, str) or domain.lower() not in fields:
        raise _GroupError(("domain",), "expected er, ws, ba, ring, or mesh")
    domain = domain.lower()
    if not isinstance(params, Mapping):
        raise _GroupError(("params",), "expected a mapping of model parameters")
    for key in params:
        if key not in fields[domain]:
            raise _GroupError(("params", str(key)), f"unknown {domain.upper()} parameter {key!r}")
    if seed is None:
        digest = sha256(f"{master_seed}:{group_id}".encode()).digest()
        seed = int.from_bytes(digest[:4], "big")
    _integer(seed, "seed")

    if domain == "er":
        p = _probability(params.get("p", min(1, 3 / max(1, n - 1))), "p")
        settings = {"p": p}
        # The skip sampler divides by log(1 - p), which rounds to zero for tiny p.
        sample = nx.gnp_random_graph if p > 0 and 1 - p == 1 else nx.fast_gnp_random_graph
        network = sample(n, p, seed=seed)
    elif domain == "ws":
        k = _integer(params.get("k", min(4, 2 * ((n - 1) // 2))), "params", "k")
        if not 0 <= k < n or k % 2:
            raise _GroupError(("params", "k"), "k must be even and satisfy 0 <= k < n")
        beta = _probability(params.get("beta", 0.1), "beta")
        settings = {"k": k, "beta": beta}
        network = nx.watts_strogatz_graph(n, k, beta, seed=seed)
    elif domain == "ba":
        m = _integer(params.get("m", min(2, n - 1)), "params", "m")
        if not 1 <= m < n:
            raise _GroupError(("params", "m"), "BA requires 1 <= m < n")
        settings = {"m": m}
        network = nx.barabasi_albert_graph(n, m, seed=seed)
    elif domain == "ring":
        settings = {}
        network = nx.cycle_graph(n) if n > 2 else nx.path_graph(n)
    else:
        settings = {}
        network = nx.complete_graph(n)

    members = tuple(f"{group_id}-{i}" for i in range(1, n + 1))
    group = Group(group_id, domain, seed, MappingProxyType(settings), members)
    return group, network.edges
