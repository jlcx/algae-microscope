"""Neighborhood exporters: text, JSON, GraphML, DOT."""

from __future__ import annotations

import json
import re
from xml.sax.saxutils import escape, quoteattr

from server.constants import CG_RELS, ENDS, OTHERS, STARTS_DEFAULT_ORDER
from server.neighborhood.model import Neighborhood

# §5.2.1 anchor policy order, used for the one-line date shown per node.
_ANCHOR_ORDER = STARTS_DEFAULT_ORDER + sorted(OTHERS) + sorted(ENDS)


_TIME_RE = re.compile(r'^([+-]\d+)-(\d\d)-(\d\d)T')


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def format_date_value(time_value: str, precision: int) -> str:
    """Precision-faithful date rendering (mirrors web formatDateValue):
    p11 → 2009-11-13, p10 → 2009-11, p9 → 1952 / 44 BCE, p8 → 1950s,
    p7 → 19th century, coarser → raw."""
    match = _TIME_RE.match(time_value)
    if not match:
        return time_value
    year = int(match.group(1))
    year_label = f"{year:04d}" if year > 0 else str(year)
    if precision >= 11:
        return f"{year_label}-{match.group(2)}-{match.group(3)}"
    if precision == 10:
        return f"{year_label}-{match.group(2)}"
    if precision == 9:
        return f"{1 - year} BCE" if year <= 0 else str(year)
    if precision == 8:
        return f"{(year // 10) * 10}s"
    if precision == 7:
        if year > 0:
            return f"{_ordinal((year - 1) // 100 + 1)} century"
        return f"{_ordinal(-year // 100 + 1)} century BCE"
    if precision == 6:
        if year > 0:
            return f"{_ordinal((year - 1) // 1000 + 1)} millennium"
        return f"{_ordinal(-year // 1000 + 1)} millennium BCE"
    return time_value


def _anchor_date(dates):
    top = [d for d in dates if not d.source_property]
    for prop in _ANCHOR_ORDER:
        candidates = [d for d in top if d.property == prop]
        if candidates:
            return max(candidates, key=lambda d: d.precision)
    return top[0] if top else None


def to_json(neighborhood: Neighborhood) -> str:
    return json.dumps(neighborhood.to_dict(), indent=2, ensure_ascii=False)


def to_text(neighborhood: Neighborhood, max_witness_langs: int = 12) -> str:
    """Terminal rendering, the original microscope use case."""
    lines = []
    nodes = neighborhood.nodes
    by_hop: dict[int, list] = {}
    for node in nodes.values():
        by_hop.setdefault(node.hop, []).append(node)

    lines.append(f"neighborhood: {len(nodes)} nodes, "
                 f"{len(neighborhood.edges)} edges "
                 f"(seeds: {', '.join(neighborhood.seeds)})")
    for hop in sorted(by_hop):
        tag = "seeds" if hop == 0 else f"hop {hop}"
        lines.append(f"\n[{tag}] {len(by_hop[hop])} nodes")
        ranked = sorted(by_hop[hop], key=lambda n: -(n.wp_count or 0))
        for node in ranked:
            wp = f" wp={node.wp_count}" if node.wp_count is not None else ""
            dated = ""
            anchor = _anchor_date(node.dates)
            if anchor:
                dated = (f" [{anchor.property} "
                         f"{format_date_value(anchor.time_value, anchor.precision)}]")
            lines.append(f"  {node.qid}  {node.label}{wp}{dated}")

    consensus = [e for e in neighborhood.edges.values() if e.kind == "consensus"]
    typed = [e for e in neighborhood.edges.values() if e.kind == "typed"]

    if consensus:
        lines.append(f"\nconsensus edges ({len(consensus)}):")
        for edge in sorted(consensus, key=lambda e: -(e.wp_count or 0)):
            label = lambda q: nodes[q].label if q in nodes else q
            eff = (f" eff={edge.effective_count:g}"
                   if edge.effective_count is not None else "")
            flag = "  ** WP-not-WD **" if edge.wp_not_wd else ""
            witness = ""
            if edge.langs is not None:
                shown = edge.langs[:max_witness_langs]
                more = len(edge.langs) - len(shown)
                witness = ("  [" + ",".join(shown)
                           + (f",+{more}" if more > 0 else "") + "]")
            lines.append(f"  {label(edge.src)} <-> {label(edge.dst)}  "
                         f"wp={edge.wp_count}{eff}{flag}{witness}")

    if typed:
        lines.append(f"\ntyped edges ({len(typed)}):")
        for edge in sorted(typed, key=lambda e: (e.prop, e.src)):
            label = lambda q: nodes[q].label if q in nodes else q
            prop_label = CG_RELS.get(edge.prop, "")
            prop = f"{edge.prop} ({prop_label})" if prop_label else edge.prop
            lines.append(f"  {label(edge.src)} -[{prop}]-> {label(edge.dst)}")

    return "\n".join(lines) + "\n"


def to_graphml(neighborhood: Neighborhood) -> str:
    """GraphML with node/edge attributes, importable into Gephi."""
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
        '  <key id="wp_count" for="node" attr.name="wp_count" attr.type="int"/>',
        '  <key id="hop" for="node" attr.name="hop" attr.type="int"/>',
        '  <key id="seed" for="node" attr.name="seed" attr.type="boolean"/>',
        '  <key id="kind" for="edge" attr.name="kind" attr.type="string"/>',
        '  <key id="prop" for="edge" attr.name="prop" attr.type="string"/>',
        '  <key id="weight" for="edge" attr.name="weight" attr.type="double"/>',
        '  <key id="wp_not_wd" for="edge" attr.name="wp_not_wd" attr.type="boolean"/>',
        '  <graph id="neighborhood" edgedefault="directed">',
    ]
    for node in neighborhood.nodes.values():
        out.append(f'    <node id={quoteattr(node.qid)}>')
        out.append(f'      <data key="label">{escape(node.label)}</data>')
        if node.wp_count is not None:
            out.append(f'      <data key="wp_count">{node.wp_count}</data>')
        out.append(f'      <data key="hop">{node.hop}</data>')
        out.append(f'      <data key="seed">{str(node.seed).lower()}</data>')
        out.append('    </node>')
    for edge in neighborhood.edges.values():
        out.append(f'    <edge id={quoteattr(edge.id)} '
                   f'source={quoteattr(edge.src)} target={quoteattr(edge.dst)}>')
        out.append(f'      <data key="kind">{edge.kind}</data>')
        if edge.kind == "typed":
            out.append(f'      <data key="prop">{escape(edge.prop or "")}</data>')
        else:
            weight = (edge.effective_count if edge.effective_count is not None
                      else edge.wp_count)
            if weight is not None:
                out.append(f'      <data key="weight">{weight}</data>')
            if edge.wp_not_wd is not None:
                out.append('      <data key="wp_not_wd">'
                           f'{str(edge.wp_not_wd).lower()}</data>')
        out.append('    </edge>')
    out.append('  </graph>')
    out.append('</graphml>')
    return "\n".join(out) + "\n"


def _dot_quote(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def to_dot(neighborhood: Neighborhood) -> str:
    out = ["digraph neighborhood {", "  overlap=false;"]
    for node in neighborhood.nodes.values():
        attrs = [f"label={_dot_quote(node.label)}"]
        if node.seed:
            attrs.append("shape=doublecircle")
        out.append(f"  {_dot_quote(node.qid)} [{', '.join(attrs)}];")
    for edge in neighborhood.edges.values():
        if edge.kind == "consensus":
            attrs = ["dir=none", "color=gray"]
            weight = (edge.effective_count if edge.effective_count is not None
                      else edge.wp_count)
            if weight is not None:
                attrs.append(f"label={_dot_quote(f'{weight:g}')}")
            if edge.wp_not_wd:
                attrs.append("color=red")
        else:
            label = CG_RELS.get(edge.prop or "", edge.prop or "")
            attrs = [f"label={_dot_quote(label)}"]
        out.append(f"  {_dot_quote(edge.src)} -> {_dot_quote(edge.dst)} "
                   f"[{', '.join(attrs)}];")
    out.append("}")
    return "\n".join(out) + "\n"


FORMATS = {
    "text": to_text,
    "json": to_json,
    "graphml": to_graphml,
    "dot": to_dot,
}
