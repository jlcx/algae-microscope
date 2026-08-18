/** Shared canvas rendering of nodes and edges (§5.1 encodings), used by both
 * views so the graph↔temporal transition animates over one scene (§5.3). */

import type { AppState, Position } from './state.ts';
import type { NEdge, NNode } from './types.ts';

export const CATEGORY_COLORS: Record<string, string> = {
  influence: '#a78bfa',
  causation: '#f87171',
  kinship: '#fbbf24',
  mentorship: '#34d399',
  creation: '#60a5fa',
  succession: '#2dd4bf',
  production: '#f472b6',
  other: '#9ca3af',
};

export const COLORS = {
  background: '#12151a',
  consensus: '#8a93a3',
  wpNotWd: '#fb923c',          // the discovery signal (§5.1)
  node: '#cbd5e1',
  nodeSeed: '#fde68a',
  nodeStroke: '#12151a',
  label: '#e2e8f0',
  labelDim: '#94a3b8',
  selection: '#38bdf8',
  compare: '#c084fc',
  axis: '#475569',
  band: 'rgba(148,163,184,0.13)',
  inferred: 'rgba(45,212,191,0.18)',
  margin: 'rgba(148,163,184,0.06)',
};

export interface RenderStyle {
  /** Muted rendering for edges into the margin dock (§5.2.3). */
  mutedNodes?: Set<string>;
}

export function nodeRadius(state: AppState, node: NNode,
                           degree: Map<string, number>): number {
  let base = 6;
  if (state.sizeBy === 'wp_count' && node.wp_count != null) {
    base = 4 + Math.sqrt(node.wp_count) * 0.9;
  } else if (state.sizeBy === 'degree') {
    base = 4 + Math.sqrt(degree.get(node.qid) ?? 1) * 1.6;
  }
  return Math.min(base, 22);
}

export function propColor(state: AppState, prop?: string): string {
  const category = prop ? state.clientConfig?.prop_categories?.[prop] : null;
  return CATEGORY_COLORS[category ?? 'other'] ?? CATEGORY_COLORS.other;
}

function edgeOffsets(edges: NEdge[]): Map<string, number> {
  // Parallel edges between the same unordered pair are distinct (§3.4);
  // spread them perpendicular so all remain visible.
  const groups = new Map<string, NEdge[]>();
  for (const edge of edges) {
    const key = edge.src < edge.dst
      ? `${edge.src}|${edge.dst}` : `${edge.dst}|${edge.src}`;
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(edge);
  }
  const offsets = new Map<string, number>();
  for (const group of groups.values()) {
    group.forEach((edge, index) => {
      offsets.set(edge.id, (index - (group.length - 1) / 2) * 7);
    });
  }
  return offsets;
}

export function drawScene(
  ctx: CanvasRenderingContext2D,
  state: AppState,
  positions: Map<string, Position>,
  style: RenderStyle = {},
): void {
  const edges = state.visibleEdges();
  const nodes = state.visibleNodes().filter(n => positions.has(n.qid));
  const degree = state.degree();
  const offsets = edgeOffsets(edges);
  const selected = state.selection;

  for (const edge of edges) {
    const a = positions.get(edge.src);
    const b = positions.get(edge.dst);
    if (!a || !b) continue;
    const muted = style.mutedNodes?.has(edge.src)
      || style.mutedNodes?.has(edge.dst);
    const offset = offsets.get(edge.id) ?? 0;
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;
    const cx = mx + nx * offset * 2.2;
    const cy = my + ny * offset * 2.2;

    const isSelected = selected?.type === 'edge' && selected.id === edge.id;
    const isCompare = state.compareEdge === edge.id;

    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.quadraticCurveTo(cx, cy, b.x, b.y);
    if (edge.kind === 'consensus') {
      const strength = state.strength(edge);
      // thickness/opacity by effective language count (§5.1)
      ctx.lineWidth = Math.min(1 + Math.sqrt(strength) * 0.75, 9);
      ctx.strokeStyle = edge.wp_not_wd ? COLORS.wpNotWd : COLORS.consensus;
      ctx.globalAlpha = muted ? 0.12
        : Math.min(0.2 + strength * 0.035, 0.85);
      ctx.setLineDash(edge.wp_not_wd ? [7, 4] : []);
    } else {
      ctx.lineWidth = 1.4;
      ctx.strokeStyle = propColor(state, edge.prop);
      ctx.globalAlpha = muted ? 0.15 : 0.7;
      ctx.setLineDash([]);
    }
    if (isSelected || isCompare) {
      ctx.globalAlpha = 1;
      ctx.lineWidth += 1.6;
      ctx.strokeStyle = isSelected ? COLORS.selection : COLORS.compare;
    }
    ctx.stroke();
    ctx.setLineDash([]);

    if (edge.kind === 'typed') {
      // arrowhead toward dst (§5.1: typed edges render directionally)
      const tx = b.x - (dx / len) * 12;
      const ty = b.y - (dy / len) * 12;
      const angle = Math.atan2(b.y - cy, b.x - cx);
      ctx.beginPath();
      ctx.moveTo(tx + Math.cos(angle) * 6, ty + Math.sin(angle) * 6);
      ctx.lineTo(tx + Math.cos(angle + 2.5) * 6, ty + Math.sin(angle + 2.5) * 6);
      ctx.lineTo(tx + Math.cos(angle - 2.5) * 6, ty + Math.sin(angle - 2.5) * 6);
      ctx.closePath();
      ctx.fillStyle = ctx.strokeStyle as string;
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (const node of nodes) {
    const p = positions.get(node.qid)!;
    const r = nodeRadius(state, node, degree);
    const muted = style.mutedNodes?.has(node.qid);
    const isSelected = selected?.type === 'node' && selected.id === node.qid;

    ctx.globalAlpha = muted ? 0.45 : 1;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fillStyle = node.seed ? COLORS.nodeSeed : COLORS.node;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = COLORS.nodeStroke;
    ctx.stroke();
    if (node.seed) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 3.5, 0, Math.PI * 2);
      ctx.strokeStyle = COLORS.nodeSeed;
      ctx.lineWidth = 1.4;
      ctx.stroke();
    }
    if (state.pinned.has(node.qid)) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
      ctx.fillStyle = COLORS.background;
      ctx.fill();
    }
    if (isSelected) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 6, 0, Math.PI * 2);
      ctx.strokeStyle = COLORS.selection;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    ctx.font = node.seed ? 'bold 12px system-ui' : '11px system-ui';
    ctx.fillStyle = muted ? COLORS.labelDim : COLORS.label;
    ctx.fillText(node.label, p.x, p.y + r + 4);
    ctx.globalAlpha = 1;
  }
}
