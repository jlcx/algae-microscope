/**
 * Temporal layout (§5.2): anchor selection, undated handling, and vertical
 * lane assignment that keeps concurrent entities apart while pulling
 * connected entities toward nearby lanes (crossing reduction heuristic).
 */

import type {
  Anchor, LayoutOptions, PositionedEntity, TemporalEdge, TemporalEntity,
  TemporalLayout,
} from './types.ts';
import {
  DEFAULT_POLICY, secondaryEvents, selectAnchor, selectEndAnchor,
} from './anchor.ts';
import { DEFAULT_RULES, inferInterval } from './infer.ts';

/** Two rows conflict when their [start, end] intervals (in years, padded a
 * touch so labels breathe) overlap. */
function interval(e: PositionedEntity, pad: number): [number, number] {
  if (e.anchor) {
    const start = e.anchor.year;
    const end = e.endAnchor ? Math.max(e.endAnchor.year, start) : start;
    return [start - pad, end + e.anchor.spanYears + pad];
  }
  const inf = e.inferred!;
  const lo = inf.min ?? inf.max! - pad * 4;
  const hi = inf.max ?? inf.min! + pad * 4;
  return [lo - pad, hi + pad];
}

export function layoutTemporal(
  entities: TemporalEntity[],
  edges: TemporalEdge[],
  options: LayoutOptions = {},
): TemporalLayout {
  const policy = options.policy ?? DEFAULT_POLICY;
  const undatedMode = options.undated ?? 'margin';
  const rules = options.rules ?? DEFAULT_RULES;

  const positioned: PositionedEntity[] = entities.map(entity => {
    const anchor = selectAnchor(entity.dates, policy);
    const endAnchor = anchor && anchor.kind !== 'end'
      ? selectEndAnchor(entity.dates, policy) : null;
    return {
      id: entity.id,
      anchor,
      endAnchor,
      inferred: null,
      region: anchor ? 'timeline' as const : 'margin' as const,
      lane: 0,
      events: secondaryEvents(entity.dates, policy),
    };
  });
  const byId = new Map(positioned.map(p => [p.id, p]));
  const anchors = new Map<string, Anchor>();
  for (const p of positioned) {
    if (p.anchor) anchors.set(p.id, p.anchor);
  }

  if (undatedMode === 'infer') {
    for (const p of positioned) {
      if (p.anchor) continue;
      const inferred = inferInterval(p.id, edges, anchors, rules);
      if (inferred) {
        p.inferred = inferred;
        p.region = 'timeline';
      }
    }
  }

  const timeline = positioned.filter(p => p.region === 'timeline');
  const dated = timeline.filter(p => p.anchor);
  let extent: [number, number] | null = null;
  if (dated.length) {
    extent = [
      Math.min(...dated.map(p => p.anchor!.year)),
      Math.max(...dated.map(p => (p.endAnchor ?? p.anchor)!.year
        + p.anchor!.spanYears)),
    ];
  }
  const pad = extent ? Math.max((extent[1] - extent[0]) / 40, 1e-9) : 1;

  // Neighbor map for the barycenter pull.
  const neighbors = new Map<string, string[]>();
  for (const edge of edges) {
    if (!byId.has(edge.src) || !byId.has(edge.dst)) continue;
    (neighbors.get(edge.src) ?? neighbors.set(edge.src, []).get(edge.src)!)
      .push(edge.dst);
    (neighbors.get(edge.dst) ?? neighbors.set(edge.dst, []).get(edge.dst)!)
      .push(edge.src);
  }

  // Greedy sweep in time order: each entity takes a lane free over its
  // interval, preferring the lane closest to the mean lane of its
  // already-placed neighbors — a single-pass barycenter heuristic that
  // reduces crossings among concurrent entities without a full solver.
  const sorted = [...timeline].sort((a, b) =>
    interval(a, pad)[0] - interval(b, pad)[0]);
  const laneEnds: number[] = []; // per lane: end of last placed interval
  const placed = new Map<string, number>();
  for (const entity of sorted) {
    const [start, end] = interval(entity, pad);
    const free: number[] = [];
    for (let lane = 0; lane < laneEnds.length; lane++) {
      if (laneEnds[lane] <= start) free.push(lane);
    }
    free.push(laneEnds.length); // opening a new lane is always possible
    const placedNeighbors = (neighbors.get(entity.id) ?? [])
      .map(n => placed.get(n))
      .filter((lane): lane is number => lane !== undefined);
    let choice = free[0];
    if (placedNeighbors.length) {
      const target = placedNeighbors.reduce((s, l) => s + l, 0)
        / placedNeighbors.length;
      choice = free.reduce((best, lane) =>
        Math.abs(lane - target) < Math.abs(best - target) ? lane : best,
        free[0]);
    }
    laneEnds[choice] = Math.max(laneEnds[choice] ?? -Infinity, end);
    placed.set(entity.id, choice);
    entity.lane = choice;
  }

  // Margin nodes stack in their own ordering.
  let marginLane = 0;
  for (const p of positioned) {
    if (p.region === 'margin') p.lane = marginLane++;
  }

  return { entities: positioned, laneCount: laneEnds.length, extent };
}
