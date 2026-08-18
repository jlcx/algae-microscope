"""Effective language counts and clone families (SPEC.md §4.2).

Raw witness counts overweight bot-generated edition clusters (the Lsjbot
cluster: ceb, war, sv, vi). Each configured family contributes at most
`family_cap` to the effective count. Per-language scalar weights generalize
family caps and anticipate endogenous edition-weighting output from ALGAE.
"""

from __future__ import annotations

from typing import Iterable


class WitnessWeights:
    def __init__(self, families: list[list[str]] | None = None,
                 family_cap: float = 1.0,
                 weights: dict[str, float] | None = None):
        self.families = [set(f) for f in (families or [])]
        self.family_cap = family_cap
        self.weights = weights or {}
        self._family_members = set().union(*self.families) if self.families else set()

    @classmethod
    def from_config(cls, config) -> "WitnessWeights":
        w = config.witnesses
        return cls(families=w.clone_families, family_cap=w.family_cap,
                   weights=w.weights)

    def weight(self, lang: str) -> float:
        return self.weights.get(lang, 1.0)

    def effective_count(self, langs: Iterable[str]) -> float:
        """|witnesses outside any family| (weighted) + per-family
        min(weighted family witnesses, cap)."""
        langs = set(langs)
        total = sum(self.weight(lang) for lang in langs
                    if lang not in self._family_members)
        for family in self.families:
            in_family = langs & family
            if in_family:
                total += min(sum(self.weight(lang) for lang in in_family),
                             self.family_cap)
        return total


def witness_set_ops(a: Iterable[str], b: Iterable[str]) -> dict:
    """Set operations across an edge pair (§4.1): shared witnesses and the
    symmetric difference, split by side."""
    sa, sb = set(a), set(b)
    return {
        "shared": sorted(sa & sb),
        "only_a": sorted(sa - sb),
        "only_b": sorted(sb - sa),
    }
