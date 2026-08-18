/**
 * Shared application state (§5.3 view continuity): graph and temporal views
 * are two projections of one neighborhood state. Selection, filters,
 * expansion state, pinned nodes, and per-node positions persist across view
 * switches; node identity is the QID.
 */

import type {
  Capabilities, ClientConfig, Delta, NEdge, NNode, Neighborhood,
  RequestFilters,
} from './types.ts';

export type Selection =
  | { type: 'node'; id: string }
  | { type: 'edge'; id: string }
  | null;

export interface Position { x: number; y: number; }

export class AppState extends EventTarget {
  neighborhood: Neighborhood | null = null;
  clientConfig: ClientConfig | null = null;
  capabilities: Capabilities | null = null;

  nodes = new Map<string, NNode>();
  edges = new Map<string, NEdge>();

  view: 'graph' | 'temporal' = 'graph';
  selection: Selection = null;
  /** Second selected consensus edge for witness set operations (§4.1). */
  compareEdge: string | null = null;
  pinned = new Set<string>();
  hidden = new Set<string>();

  // Display filters/toggles (client-side).
  useEffective = true;           // §4.2 raw vs effective toggle
  witnessFilter = '';            // §4.1 "only edges witnessed by <lang>"
  minStrength = 0;
  showConsensus = true;
  showTyped = true;
  sizeBy: 'uniform' | 'degree' | 'wp_count' = 'wp_count';
  undatedMode: 'margin' | 'infer' = 'margin';
  showAllEvents = false;         // §5.2.4 default: lifespan bars only

  // Request parameters (also the permalink payload).
  seeds: string[] = [];
  hops = 1;
  budget = 100;
  filters: RequestFilters = { props: 'all', direction: 'both' };

  /** Animated screen positions, shared across views so transitions can
   * interpolate (§5.3). */
  positions = new Map<string, Position>();

  busy = false;
  error = '';

  emit(kind = 'change'): void {
    this.dispatchEvent(new Event(kind));
  }

  setNeighborhood(n: Neighborhood): void {
    this.neighborhood = n;
    this.capabilities = n.backend.capabilities;
    this.nodes.clear();
    this.edges.clear();
    this.hidden.clear();
    this.compareEdge = null;
    this.selection = null;
    for (const node of n.nodes) this.nodes.set(node.qid, node);
    for (const edge of n.edges) this.edges.set(edge.id, edge);
    for (const qid of this.positions.keys()) {
      if (!this.nodes.has(qid)) this.positions.delete(qid);
    }
    this.emit();
  }

  mergeDelta(delta: Delta, around: string): void {
    const origin = this.positions.get(around);
    let i = 0;
    for (const node of delta.nodes) {
      if (!this.nodes.has(node.qid)) {
        this.nodes.set(node.qid, node);
        if (origin) {
          // spawn near the expanded node so the sim untangles locally
          const angle = (i++ / Math.max(delta.nodes.length, 1)) * Math.PI * 2;
          this.positions.set(node.qid, {
            x: origin.x + Math.cos(angle) * 40,
            y: origin.y + Math.sin(angle) * 40,
          });
        }
      }
    }
    for (const edge of delta.edges) {
      if (!this.edges.has(edge.id)) this.edges.set(edge.id, edge);
    }
    this.emit();
  }

  /** Effective-or-raw strength of a consensus edge under current toggles. */
  strength(edge: NEdge): number {
    if (this.useEffective && edge.effective_count != null) {
      return edge.effective_count;
    }
    return edge.wp_count ?? 0;
  }

  /** Edges passing the client-side display filters, endpoints visible. */
  visibleEdges(): NEdge[] {
    const result: NEdge[] = [];
    for (const edge of this.edges.values()) {
      if (this.hidden.has(edge.src) || this.hidden.has(edge.dst)) continue;
      if (edge.kind === 'consensus') {
        if (!this.showConsensus) continue;
        if (this.strength(edge) < this.minStrength) continue;
        if (this.witnessFilter
            && !(edge.langs ?? []).includes(this.witnessFilter)) continue;
      } else if (!this.showTyped) {
        continue;
      }
      result.push(edge);
    }
    return result;
  }

  visibleNodes(): NNode[] {
    return [...this.nodes.values()].filter(n => !this.hidden.has(n.qid));
  }

  degree(): Map<string, number> {
    const deg = new Map<string, number>();
    for (const edge of this.edges.values()) {
      deg.set(edge.src, (deg.get(edge.src) ?? 0) + 1);
      deg.set(edge.dst, (deg.get(edge.dst) ?? 0) + 1);
    }
    return deg;
  }

  select(sel: Selection, additive = false): void {
    if (additive && sel?.type === 'edge' && this.selection?.type === 'edge'
        && sel.id !== this.selection.id) {
      this.compareEdge = sel.id;
    } else {
      this.selection = sel;
      this.compareEdge = null;
    }
    this.emit();
  }

  permalink(): string {
    return '#' + encodeURIComponent(JSON.stringify({
      seeds: this.seeds, hops: this.hops, budget: this.budget,
      filters: this.filters, view: this.view,
    }));
  }

  loadPermalink(hash: string): boolean {
    try {
      const data = JSON.parse(decodeURIComponent(hash.replace(/^#/, '')));
      if (!Array.isArray(data.seeds) || !data.seeds.length) return false;
      this.seeds = data.seeds;
      this.hops = data.hops ?? this.hops;
      this.budget = data.budget ?? this.budget;
      this.filters = data.filters ?? this.filters;
      if (data.view === 'temporal' || data.view === 'graph') {
        this.view = data.view;
      }
      return true;
    } catch {
      return false;
    }
  }
}
