/** App entry: wires state, views, controls, panel; runs the render loop
 * that animates shared node positions toward the active view's targets so
 * graph↔temporal switches keep orientation (§5.3). */

import { api } from './api.ts';
import { AppState } from './state.ts';
import { GraphView } from './graph/graphview.ts';
import { TemporalView } from './temporalview.ts';
import { Controls } from './controls.ts';
import { Panel } from './panel.ts';
import { COLORS, drawScene, nodeRadius } from './render.ts';
import type { ViewMode } from './viewmode.ts';
import type { NEdge } from './types.ts';
import { DEFAULT_POLICY, selectAnchor, withPriority } from './temporal/index.ts';

const state = new AppState();
const canvas = document.getElementById('stage') as HTMLCanvasElement;
const ctx = canvas.getContext('2d')!;

const views: Record<'graph' | 'temporal', ViewMode> = {
  graph: new GraphView(state),
  temporal: new TemporalView(state),
};

function activeView(): ViewMode {
  return views[state.view];
}

async function load(): Promise<void> {
  if (state.busy) return; // a load can take a while on hub-heavy frontiers
  state.busy = true;
  state.error = '';
  state.emit();
  try {
    const neighborhood = await api.neighborhood(
      state.seeds, state.hops, state.budget, state.filters);
    state.setNeighborhood(neighborhood);
    history.replaceState(null, '', state.permalink());
    views.graph.refresh();
    views.temporal.refresh();
  } catch (err) {
    state.error = String(err instanceof Error ? err.message : err);
  } finally {
    state.busy = false;
    state.emit();
  }
}

async function expandNode(qid: string): Promise<void> {
  if (state.busy) return;
  state.busy = true;
  state.emit();
  try {
    const delta = await api.expand(
      [...state.nodes.keys()], qid, state.budget, state.filters);
    state.mergeDelta(delta, qid);
    views.graph.refresh();
    views.temporal.refresh();
  } catch (err) {
    state.error = String(err instanceof Error ? err.message : err);
  } finally {
    state.busy = false;
    state.emit();
  }
}

new Controls(document.getElementById('toolbar')!, state, { load });
new Panel(document.getElementById('panel')!, state, { expand: expandNode });

state.addEventListener('change', () => activeView().refresh());
state.addEventListener('viewchange', () => activeView().refresh());

// --- canvas sizing ---

function resize(): void {
  const rect = canvas.parentElement!.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
window.addEventListener('resize', resize);
resize();

// --- hit testing ---

function hitNode(x: number, y: number): string | null {
  const degree = state.degree();
  let best: string | null = null;
  let bestDist = Infinity;
  for (const node of state.visibleNodes()) {
    const p = state.positions.get(node.qid);
    if (!p) continue;
    const dist = Math.hypot(p.x - x, p.y - y);
    const r = nodeRadius(state, node, degree) + 5;
    if (dist < r && dist < bestDist) {
      best = node.qid;
      bestDist = dist;
    }
  }
  return best;
}

function segmentDistance(px: number, py: number, ax: number, ay: number,
                         bx: number, by: number): number {
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function hitEdge(x: number, y: number): NEdge | null {
  let best: NEdge | null = null;
  let bestDist = 6;
  for (const edge of state.visibleEdges()) {
    const a = state.positions.get(edge.src);
    const b = state.positions.get(edge.dst);
    if (!a || !b) continue;
    const dist = segmentDistance(x, y, a.x, a.y, b.x, b.y);
    if (dist < bestDist) {
      best = edge;
      bestDist = dist;
    }
  }
  return best;
}

// --- pointer interactions ---

let dragging = false;
let dragMoved = false;
let lastX = 0;
let lastY = 0;
let hover: { x: number; y: number; text: string[] } | null = null;

canvas.addEventListener('pointerdown', e => {
  const { offsetX: x, offsetY: y } = e;
  const nodeId = hitNode(x, y);
  if (activeView().onDragStart(x, y, nodeId)) {
    dragging = true;
    dragMoved = false;
    lastX = x;
    lastY = y;
    canvas.setPointerCapture(e.pointerId);
  }
});

canvas.addEventListener('pointermove', e => {
  const { offsetX: x, offsetY: y } = e;
  if (dragging) {
    const dx = x - lastX;
    const dy = y - lastY;
    if (Math.abs(dx) + Math.abs(dy) > 1) dragMoved = true;
    activeView().onDragMove(dx, dy, x, y);
    lastX = x;
    lastY = y;
    return;
  }
  const nodeId = hitNode(x, y);
  if (nodeId) {
    const node = state.nodes.get(nodeId)!;
    const lines = [`${node.label} (${nodeId})`];
    if (node.wp_count != null) lines.push(`wp_count ${node.wp_count}`);
    if (state.view === 'temporal' && node.dates.length) {
      const policy = withPriority(DEFAULT_POLICY,
        state.clientConfig?.temporal.anchor_priority ?? []);
      const anchor = selectAnchor(node.dates, policy);
      if (anchor?.conflict) {
        lines.push(`⚠ conflicting ${anchor.property} values in Wikidata`);
      }
      if (anchor?.kind === 'end') {
        lines.push('positioned at its end date (no start date known)');
      }
    }
    hover = { x, y, text: lines };
    canvas.style.cursor = 'pointer';
    return;
  }
  const edge = hitEdge(x, y);
  if (edge) {
    const lines: string[] = [];
    if (edge.kind === 'typed') {
      const propLabel = state.clientConfig?.cg_rels?.[edge.prop ?? ''];
      lines.push(`${edge.prop}${propLabel ? ` ${propLabel}` : ''}`);
    } else {
      lines.push(`consensus wp=${edge.wp_count}`
        + (edge.effective_count != null
           ? ` eff=${(+edge.effective_count).toFixed(1)}` : ''));
      if (edge.wp_not_wd) lines.push('WP-not-WD');
    }
    hover = { x, y, text: lines };
    canvas.style.cursor = 'pointer';
    return;
  }
  hover = null;
  canvas.style.cursor = 'default';
});

canvas.addEventListener('pointerup', e => {
  const { offsetX: x, offsetY: y } = e;
  const wasDrag = dragging && dragMoved;
  if (dragging) {
    activeView().onDragEnd();
    dragging = false;
  }
  if (wasDrag) return;
  const nodeId = hitNode(x, y);
  if (nodeId) {
    state.select({ type: 'node', id: nodeId });
    return;
  }
  const edge = hitEdge(x, y);
  if (edge) {
    state.select({ type: 'edge', id: edge.id }, e.shiftKey);
    return;
  }
  state.select(null);
});

canvas.addEventListener('dblclick', e => {
  const nodeId = hitNode(e.offsetX, e.offsetY);
  if (nodeId) expandNode(nodeId); // click-to-expand (§5.1)
});

canvas.addEventListener('wheel', e => {
  e.preventDefault();
  activeView().onWheel(e, e.offsetX, e.offsetY);
}, { passive: false });

// --- render loop ---

const LERP = 0.16;

function frame(): void {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const targets = activeView().targets(width, height);

  for (const [qid, target] of targets) {
    const current = state.positions.get(qid);
    if (!current) {
      state.positions.set(qid, { ...target });
    } else {
      current.x += (target.x - current.x) * LERP;
      current.y += (target.y - current.y) * LERP;
    }
  }

  ctx.fillStyle = COLORS.background;
  ctx.fillRect(0, 0, width, height);
  activeView().drawUnder(ctx, width, height);
  drawScene(ctx, state, state.positions, activeView().renderStyle());
  activeView().drawOver(ctx, width, height);

  if (hover) {
    ctx.font = '12px system-ui';
    const textWidth = Math.max(...hover.text.map(t => ctx.measureText(t).width));
    const hx = Math.min(hover.x + 14, width - textWidth - 18);
    const hy = Math.min(hover.y + 14, height - hover.text.length * 16 - 12);
    ctx.fillStyle = 'rgba(15,20,28,0.92)';
    ctx.fillRect(hx - 6, hy - 4, textWidth + 12, hover.text.length * 16 + 8);
    ctx.strokeStyle = '#334155';
    ctx.strokeRect(hx - 6, hy - 4, textWidth + 12, hover.text.length * 16 + 8);
    ctx.fillStyle = COLORS.label;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    hover.text.forEach((line, i) => ctx.fillText(line, hx, hy + i * 16));
  }

  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// --- boot ---

async function boot(): Promise<void> {
  try {
    const [config, caps] = await Promise.all([api.config(), api.capabilities()]);
    state.clientConfig = config;
    state.capabilities = caps;
    state.hops = config.expansion.default_hops;
    state.budget = config.expansion.default_budget;
    state.undatedMode = config.temporal.undated;
    state.emit();
  } catch (err) {
    state.error = `server unreachable: ${err instanceof Error ? err.message : err}`;
    state.emit();
    return;
  }
  if (location.hash.length > 1 && state.loadPermalink(location.hash)) {
    await load();
  }
}
boot();
