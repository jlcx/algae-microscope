/** Graph view (§5.1): force-directed node-link rendering with pan/zoom,
 * node dragging (pins), and click-to-expand handled by main.ts. */

import type { AppState, Position } from '../state.ts';
import type { ViewMode } from '../viewmode.ts';
import type { RenderStyle } from '../render.ts';
import { ForceSim } from './force.ts';

export class GraphView implements ViewMode {
  private sim = new ForceSim();
  private camera = { x: 0, y: 0, k: 1 };
  private dragNode: string | null = null;
  private panning = false;
  private centered = false;

  constructor(private state: AppState) {}

  private toScreen(x: number, y: number, w: number, h: number): Position {
    return {
      x: w / 2 + (x - this.camera.x) * this.camera.k,
      y: h / 2 + (y - this.camera.y) * this.camera.k,
    };
  }

  private toWorld(sx: number, sy: number, w: number, h: number): Position {
    return {
      x: this.camera.x + (sx - w / 2) / this.camera.k,
      y: this.camera.y + (sy - h / 2) / this.camera.k,
    };
  }

  refresh(): void {
    const nodes = this.state.visibleNodes();
    const maxStrength = Math.max(
      1, ...this.state.visibleEdges()
        .filter(e => e.kind === 'consensus')
        .map(e => this.state.strength(e)));
    const edges = this.state.visibleEdges().map(e => ({
      src: e.src,
      dst: e.dst,
      weight: e.kind === 'consensus'
        ? 0.4 + (this.state.strength(e) / maxStrength) * 1.2
        : 0.5,
    }));
    // seed new sim nodes from current animated positions (view continuity)
    const initial = new Map<string, Position>();
    for (const [qid, p] of this.state.positions) {
      // screen→world under current camera; width/height unknown here, so
      // approximate with the last-used transform via inverse of toScreen at
      // origin — good enough as a starting point for the sim
      initial.set(qid, {
        x: this.camera.x + (p.x - this.lastW / 2) / this.camera.k,
        y: this.camera.y + (p.y - this.lastH / 2) / this.camera.k,
      });
    }
    this.sim.setGraph(nodes.map(n => n.qid), edges, initial);
    for (const qid of this.state.pinned) {
      const simNode = this.sim.nodes.get(qid);
      if (simNode) simNode.pinned = true;
    }
  }

  private lastW = 800;
  private lastH = 600;

  targets(width: number, height: number): Map<string, Position> {
    this.lastW = width;
    this.lastH = height;
    this.sim.tick();
    const result = new Map<string, Position>();
    for (const node of this.sim.nodes.values()) {
      result.set(node.id, this.toScreen(node.x, node.y, width, height));
    }
    if (!this.centered && this.sim.nodes.size) {
      this.centered = true;
    }
    return result;
  }

  drawUnder(): void { /* no chrome under the graph */ }
  drawOver(): void { /* tooltips handled globally */ }
  renderStyle(): RenderStyle { return {}; }

  onWheel(e: WheelEvent, x: number, y: number): void {
    const factor = Math.exp(-e.deltaY * 0.0015);
    const before = this.toWorld(x, y, this.lastW, this.lastH);
    this.camera.k = Math.min(Math.max(this.camera.k * factor, 0.1), 6);
    const after = this.toWorld(x, y, this.lastW, this.lastH);
    this.camera.x += before.x - after.x;
    this.camera.y += before.y - after.y;
  }

  onDragStart(_x: number, _y: number, nodeId: string | null): boolean {
    if (nodeId) {
      this.dragNode = nodeId;
      const simNode = this.sim.nodes.get(nodeId);
      if (simNode) simNode.pinned = true;
      return true;
    }
    this.panning = true;
    return true;
  }

  onDragMove(dx: number, dy: number, x: number, y: number): void {
    if (this.dragNode) {
      const simNode = this.sim.nodes.get(this.dragNode);
      if (simNode) {
        const world = this.toWorld(x, y, this.lastW, this.lastH);
        simNode.x = world.x;
        simNode.y = world.y;
        this.sim.reheat(0.3);
      }
    } else if (this.panning) {
      this.camera.x -= dx / this.camera.k;
      this.camera.y -= dy / this.camera.k;
    }
  }

  onDragEnd(): void {
    if (this.dragNode) {
      // dragging pins the node (§5.1); unpin via the panel
      this.state.pinned.add(this.dragNode);
      this.state.emit();
    }
    this.dragNode = null;
    this.panning = false;
  }
}
