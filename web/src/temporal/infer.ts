/**
 * Bounded single-pass constraint inference for undated nodes (§5.2.3,
 * optional strategy). Full temporal constraint propagation is CauseGraph
 * territory (§9.4); this only looks one edge deep at dated neighbors.
 */

import type { Anchor, InferenceRules, TemporalEdge } from './types.ts';

/** Default rules mirroring back_edges.py DST_EARLIER / SRC_EARLIER plus the
 * succession pairs called out in §5.2.3. */
export const DEFAULT_RULES: InferenceRules = {
  srcEarlier: ['P1542', 'P1536', 'P1537', 'P156', 'P1366', 'P167', 'P4969',
               'P800', 'P175'],
  dstEarlier: ['P737', 'P941', 'P2675', 'P144', 'P828', 'P1478', 'P1479',
               'P155', 'P1365', 'P138', 'P8371', 'P6166', 'P5707', 'P1625',
               'P6439', 'P1877', 'P5059', 'P629', 'P9810', 'P5191', 'P3342',
               'P170', 'P50', 'P86', 'P87', 'P178', 'P287', 'P943', 'P193',
               'P676', 'P84', 'P110', 'P1779', 'P162', 'P272', 'P2515',
               'P4805', 'P2554', 'P1040', 'P3092', 'P344', 'P1431', 'P161',
               'P58', 'P57', 'P6338', 'P176', 'P3919'],
  nonspecific: ['P828', 'P1542', 'P1478', 'P1536', 'P1479', 'P1537'],
};

/**
 * Infer a feasible interval for an undated node from its dated neighbors via
 * directed edges whose properties imply temporal order. Returns null when no
 * usable constraint exists. Statements with nonspecific properties and no
 * date of their own are treated as generic claims and skipped.
 */
export function inferInterval(
  nodeId: string,
  edges: TemporalEdge[],
  anchors: ReadonlyMap<string, Anchor>,
  rules: InferenceRules = DEFAULT_RULES,
): { min: number | null; max: number | null } | null {
  let min: number | null = null;
  let max: number | null = null;
  for (const edge of edges) {
    if (!edge.directed || !edge.prop) continue;
    if (rules.nonspecific.includes(edge.prop) && !edge.dated) continue;
    const isSrc = edge.src === nodeId;
    const isDst = edge.dst === nodeId;
    if (!isSrc && !isDst) continue;
    const neighbor = anchors.get(isSrc ? edge.dst : edge.src);
    if (!neighbor) continue;
    const y = neighbor.year;
    // src must begin before dst ends / dst must begin before src ends: each
    // gives a one-sided bound on the undated node's position.
    const nodeEarlier =
      (rules.srcEarlier.includes(edge.prop) && isSrc) ||
      (rules.dstEarlier.includes(edge.prop) && isDst);
    const nodeLater =
      (rules.srcEarlier.includes(edge.prop) && isDst) ||
      (rules.dstEarlier.includes(edge.prop) && isSrc);
    if (nodeEarlier) {
      max = max === null ? y : Math.min(max, y);
    } else if (nodeLater) {
      min = min === null ? y : Math.max(min, y);
    }
  }
  if (min === null && max === null) return null;
  return { min, max };
}
