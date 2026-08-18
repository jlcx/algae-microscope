/** Small force-directed layout (§5.1): spring-electric model with velocity
 * damping. O(n²) repulsion is fine at neighborhood sizes (≤ a few hundred). */

export interface SimNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  pinned: boolean;
  mass: number;
}

export interface SimEdge {
  src: string;
  dst: string;
  weight: number; // spring strength multiplier
}

const REPULSION = 3200;
const SPRING_LENGTH = 110;
const SPRING_K = 0.015;
const CENTER_PULL = 0.012;
const DAMPING = 0.85;
const MAX_SPEED = 18;

export class ForceSim {
  nodes = new Map<string, SimNode>();
  private edges: SimEdge[] = [];
  private alpha = 1;

  setGraph(ids: string[], edges: SimEdge[],
           initial?: Map<string, { x: number; y: number }>): void {
    const kept = new Map<string, SimNode>();
    let i = 0;
    for (const id of ids) {
      const existing = this.nodes.get(id);
      if (existing) {
        kept.set(id, existing);
      } else {
        const seedPos = initial?.get(id);
        // deterministic spiral placement for new nodes without a position
        const angle = i * 2.39996; // golden angle
        const radius = 60 + 14 * Math.sqrt(i);
        kept.set(id, {
          id,
          x: seedPos?.x ?? Math.cos(angle) * radius,
          y: seedPos?.y ?? Math.sin(angle) * radius,
          vx: 0, vy: 0, pinned: false, mass: 1,
        });
      }
      i++;
    }
    this.nodes = kept;
    this.edges = edges.filter(e => kept.has(e.src) && kept.has(e.dst));
    this.reheat();
  }

  reheat(alpha = 1): void {
    this.alpha = Math.max(this.alpha, alpha);
  }

  get settled(): boolean {
    return this.alpha < 0.005;
  }

  tick(): void {
    if (this.settled) return;
    const nodes = [...this.nodes.values()];
    const n = nodes.length;
    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < n; j++) {
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) { dx = (i - j) * 0.1 || 0.1; dy = 0.1; d2 = 0.02; }
        const force = (REPULSION * this.alpha) / d2;
        const d = Math.sqrt(d2);
        const fx = (dx / d) * force;
        const fy = (dy / d) * force;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      }
    }
    for (const edge of this.edges) {
      const a = this.nodes.get(edge.src)!;
      const b = this.nodes.get(edge.dst)!;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const stretch = (d - SPRING_LENGTH) * SPRING_K * edge.weight * this.alpha;
      const fx = (dx / d) * stretch;
      const fy = (dy / d) * stretch;
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
    }
    for (const node of nodes) {
      if (node.pinned) { node.vx = 0; node.vy = 0; continue; }
      node.vx = (node.vx - node.x * CENTER_PULL * this.alpha) * DAMPING;
      node.vy = (node.vy - node.y * CENTER_PULL * this.alpha) * DAMPING;
      const speed = Math.hypot(node.vx, node.vy);
      if (speed > MAX_SPEED) {
        node.vx *= MAX_SPEED / speed;
        node.vy *= MAX_SPEED / speed;
      }
      node.x += node.vx;
      node.y += node.vy;
    }
    this.alpha *= 0.985;
  }
}
