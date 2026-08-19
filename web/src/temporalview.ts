/** Temporal view (§5.2): nodes on a zoomable precision-aware time axis,
 * lanes minimizing overlap among concurrent entities, undated nodes docked
 * in a margin (or constraint-inferred bands), secondary event ticks. */

import type { AppState, Position } from './state.ts';
import type { ViewMode } from './viewmode.ts';
import type { RenderStyle } from './render.ts';
import { COLORS } from './render.ts';
import {
  DEFAULT_POLICY, TimeScale, formatDateValue, formatYear, layoutTemporal,
  precisionExtent, withPriority,
} from './temporal/index.ts';
import { propLabel } from './proplabels.ts';
import type {
  AnchorPolicy, PositionedEntity, TemporalEdge, TemporalLayout,
} from './temporal/index.ts';

const TOP_PAD = 64;
const ROW_H = 34;
const DOCK_W = 220;
const MARGIN_ROW_H = 24;

export class TemporalView implements ViewMode {
  private scale: TimeScale | null = null;
  private layout: TemporalLayout | null = null;
  private scrollY = 0;
  private dirty = true;
  private lastW = 800;
  private tickHits: { x: number; y: number; lines: string[] }[] = [];

  constructor(private state: AppState) {
    state.addEventListener('change', () => { this.dirty = true; });
  }

  refresh(): void {
    this.dirty = true;
  }

  private policy(): AnchorPolicy {
    const priority = this.state.clientConfig?.temporal.anchor_priority ?? [];
    return withPriority(DEFAULT_POLICY, priority);
  }

  private relayout(width: number): void {
    const nodes = this.state.visibleNodes();
    const edges: TemporalEdge[] = this.state.visibleEdges().map(e => ({
      src: e.src,
      dst: e.dst,
      prop: e.prop,
      directed: e.kind === 'typed',
      // a typed statement is dated when a nested date claim on src names it
      dated: e.kind === 'typed' && this.state.nodes.get(e.src)?.dates.some(
        d => d.source_property === e.prop && d.source_target === e.dst),
    }));
    this.layout = layoutTemporal(
      nodes.map(n => ({ id: n.qid, dates: n.dates })),
      edges,
      { policy: this.policy(), undated: this.state.undatedMode });
    if (!this.scale && this.layout.extent) {
      const [min, max] = this.layout.extent;
      const pad = Math.max((max - min) * 0.06, 1);
      this.scale = new TimeScale(min - pad, max + pad,
                                 70, width - DOCK_W - 30);
    } else if (this.scale) {
      this.scale.rangeMax = width - DOCK_W - 30;
    }
    this.dirty = false;
  }

  /** Point position for an entity: anchor year, or extent midpoint for
   * values coarser than the viewport (§5.2.2 spanning bands). */
  private entityX(entity: PositionedEntity): number {
    const scale = this.scale!;
    if (entity.anchor) {
      const [lo, hi] = precisionExtent(entity.anchor.year,
                                       entity.anchor.precision);
      if (hi - lo > scale.span * 0.9) {
        // coarser than the viewport: centered in the visible overlap
        const vLo = Math.max(lo, scale.domainMin);
        const vHi = Math.min(hi, scale.domainMax);
        return scale.toPx((vLo + vHi) / 2);
      }
      return scale.toPx(entity.anchor.year);
    }
    const inf = entity.inferred!;
    const lo = inf.min ?? scale.domainMin;
    const hi = inf.max ?? scale.domainMax;
    return scale.toPx((lo + hi) / 2);
  }

  private rowY(lane: number): number {
    return TOP_PAD + 26 + lane * ROW_H - this.scrollY;
  }

  targets(width: number, height: number): Map<string, Position> {
    this.lastW = width;
    if (this.dirty || !this.layout) this.relayout(width);
    const result = new Map<string, Position>();
    if (!this.layout) return result;
    for (const entity of this.layout.entities) {
      if (entity.region === 'timeline' && this.scale) {
        result.set(entity.id,
                   { x: this.entityX(entity), y: this.rowY(entity.lane) });
      } else {
        result.set(entity.id, {
          x: width - DOCK_W / 2,
          y: TOP_PAD + 20 + entity.lane * MARGIN_ROW_H - this.scrollY,
        });
      }
    }
    return result;
  }

  renderStyle(): RenderStyle {
    const muted = new Set<string>();
    for (const entity of this.layout?.entities ?? []) {
      if (entity.region === 'margin') muted.add(entity.id);
    }
    return { mutedNodes: muted };
  }

  drawUnder(ctx: CanvasRenderingContext2D, width: number,
            height: number): void {
    if (this.dirty || !this.layout) this.relayout(width);
    this.tickHits = [];
    const scale = this.scale;

    // margin dock (§5.2.3 margin placement)
    ctx.fillStyle = COLORS.margin;
    ctx.fillRect(width - DOCK_W, 0, DOCK_W, height);
    ctx.fillStyle = COLORS.labelDim;
    ctx.font = '11px system-ui';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('undated', width - DOCK_W / 2, 10);

    if (!scale) {
      ctx.fillText('no dated entities in this neighborhood', width / 2, 30);
      return;
    }

    // axis + precision-aware ticks (§5.2.2)
    ctx.strokeStyle = COLORS.axis;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(scale.rangeMin, TOP_PAD);
    ctx.lineTo(scale.rangeMax, TOP_PAD);
    ctx.stroke();
    for (const tick of scale.ticks()) {
      const x = scale.toPx(tick.year);
      ctx.globalAlpha = tick.major ? 0.9 : 0.5;
      ctx.beginPath();
      ctx.moveTo(x, TOP_PAD - (tick.major ? 8 : 5));
      ctx.lineTo(x, TOP_PAD);
      ctx.stroke();
      ctx.globalAlpha = 0.12;
      ctx.beginPath();
      ctx.moveTo(x, TOP_PAD);
      ctx.lineTo(x, height);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = tick.major ? COLORS.label : COLORS.labelDim;
      ctx.textBaseline = 'bottom';
      ctx.fillText(tick.label, x, TOP_PAD - 10);
    }

    // per-entity bands and bars
    for (const entity of this.layout!.entities) {
      if (entity.region !== 'timeline') continue;
      const y = this.rowY(entity.lane);
      if (y < TOP_PAD - ROW_H || y > height + ROW_H) continue;

      if (entity.anchor) {
        const [lo, hi] = precisionExtent(entity.anchor.year,
                                         entity.anchor.precision);
        const x0 = Math.max(scale.toPx(lo), scale.rangeMin);
        const x1 = Math.min(scale.toPx(hi), scale.rangeMax);
        // uncertainty extent — collapses to nothing at coarse zoom (§5.2.2)
        if (x1 - x0 > 4) {
          ctx.fillStyle = COLORS.band;
          ctx.fillRect(x0, y - 7, x1 - x0, 14);
        }
        // lifespan bar when both start and end anchors exist (§5.2.4)
        if (entity.endAnchor) {
          const ex = Math.min(scale.toPx(entity.endAnchor.year),
                              scale.rangeMax);
          const sx = Math.max(scale.toPx(entity.anchor.year), scale.rangeMin);
          if (ex > sx) {
            ctx.fillStyle = 'rgba(96,165,250,0.25)';
            ctx.fillRect(sx, y - 3, ex - sx, 6);
          }
        }
        // secondary event ticks (§5.2.4), beyond start/end
        if (this.state.showAllEvents) {
          for (const event of entity.events) {
            if (event.kind === 'start') continue;
            const x = scale.toPx(event.year);
            if (x < scale.rangeMin || x > scale.rangeMax) continue;
            ctx.strokeStyle = event.kind === 'nested'
              ? '#c084fc' : event.kind === 'end' ? '#f87171' : '#94a3b8';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(x, y - 10);
            ctx.lineTo(x, y - 4);
            ctx.stroke();

            const node = this.state.nodes.get(entity.id);
            const when = event.timeValue
              ? formatDateValue(event.timeValue, event.precision)
              : formatYear(event.year, event.spanYears);
            const lines = [
              `${node?.label ?? entity.id}: `
              + `${propLabel(event.property)} · ${when}`,
            ];
            if (event.sourceProperty) {
              const target = event.sourceTarget
                ? (this.state.nodes.get(event.sourceTarget)?.label
                   ?? event.sourceTarget) : '';
              const parent = propLabel(event.sourceProperty,
                                       this.state.clientConfig?.cg_rels);
              lines.push(`dates the claim ${parent}`
                + (target ? ` → ${target}` : ''));
            }
            this.tickHits.push({ x, y: y - 7, lines });
          }
        }
      } else if (entity.inferred) {
        // inferred feasible interval: wide band with marker (§5.2.3)
        const lo = entity.inferred.min ?? scale.domainMin;
        const hi = entity.inferred.max ?? scale.domainMax;
        const x0 = Math.max(scale.toPx(lo), scale.rangeMin);
        const x1 = Math.min(scale.toPx(hi), scale.rangeMax);
        ctx.fillStyle = COLORS.inferred;
        ctx.fillRect(x0, y - 8, Math.max(x1 - x0, 6), 16);
        ctx.fillStyle = COLORS.labelDim;
        ctx.font = '9px system-ui';
        ctx.textBaseline = 'middle';
        ctx.textAlign = 'left';
        ctx.fillText('inferred', Math.max(x0, scale.rangeMin) + 3, y - 14);
        ctx.textAlign = 'center';
        ctx.font = '11px system-ui';
      }
    }

    if (this.state.showAllEvents) {
      // tick legend; each tick also explains itself on hover
      const entries: [string, string][] = [
        ['#f87171', 'end date'],
        ['#c084fc', 'date on a claim'],
        ['#94a3b8', 'other dated claim'],
      ];
      let x = scale.rangeMin;
      const y = height - 12;
      ctx.font = '11px system-ui';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      for (const [color, text] of entries) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x, y - 4);
        ctx.lineTo(x, y + 4);
        ctx.stroke();
        ctx.fillStyle = COLORS.labelDim;
        ctx.fillText(text, x + 6, y);
        x += ctx.measureText(text).width + 26;
      }
      ctx.textAlign = 'center';
    }
  }

  tooltipAt(x: number, y: number): string[] | null {
    for (const tick of this.tickHits) {
      if (Math.abs(tick.x - x) <= 4 && Math.abs(tick.y - y) <= 7) {
        return tick.lines;
      }
    }
    return null;
  }

  drawOver(ctx: CanvasRenderingContext2D): void {
    if (!this.layout || !this.scale) return;
    // warning + end-anchored markers above nodes
    for (const entity of this.layout.entities) {
      if (entity.region !== 'timeline' || !entity.anchor) continue;
      const p = this.state.positions.get(entity.id);
      if (!p) continue;
      if (entity.anchor.conflict) {
        ctx.fillStyle = '#facc15';
        ctx.font = 'bold 11px system-ui';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText('!', p.x + 9, p.y - 6);
      }
      if (entity.anchor.kind === 'end') {
        // end-anchored: positioned at its end date, flagged (§5.2.1)
        ctx.strokeStyle = '#f87171';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(p.x - 12, p.y - 6);
        ctx.lineTo(p.x - 17, p.y);
        ctx.lineTo(p.x - 12, p.y + 6);
        ctx.stroke();
      }
    }
  }

  onWheel(e: WheelEvent, x: number, _y: number): void {
    if (!this.scale) return;
    if (e.shiftKey) {
      this.scrollY += e.deltaY;
      this.scrollY = Math.max(0, this.scrollY);
      return;
    }
    if (x <= this.lastW - DOCK_W) {
      this.scale.zoom(Math.exp(-e.deltaY * 0.0015), x);
    } else {
      this.scrollY = Math.max(0, this.scrollY + e.deltaY);
    }
  }

  onDragStart(_x: number, _y: number, nodeId: string | null): boolean {
    return nodeId === null; // panning only; positions are layout-owned
  }

  onDragMove(dx: number, dy: number): void {
    this.scale?.pan(dx);
    this.scrollY = Math.max(0, this.scrollY - dy);
  }

  onDragEnd(): void { /* nothing to finalize */ }
}
