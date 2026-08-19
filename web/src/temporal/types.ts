/**
 * Temporal layout module (SPEC.md §5.2): positions entities along a time
 * axis from Wikidata date claims.
 *
 * Separable by design — data in, layout out, no microscope-specific
 * dependencies — so it can later be extracted for reuse by CauseGraph. The
 * data model keeps per-node event lists rather than a single scalar
 * position, so branching visualizations are not precluded (§9.5).
 */

/** A date claim in ms_dates shape. */
export interface TemporalDateClaim {
  property: string;
  time_value: string;      // Wikidata time string, e.g. "+1952-03-11T00:00:00Z"
  precision: number;       // 0 (Ga) .. 14 (seconds)
  source_property?: string; // nested: parent claim's property ('' if top-level)
  source_target?: string;   // nested: parent claim's target
  calendarmodel?: string;   // optional Q1985727 (Gregorian) / Q1985786 (Julian)
}

export interface TemporalEntity {
  id: string;
  dates: TemporalDateClaim[];
}

/** A directed relationship used for lane assignment and inference. */
export interface TemporalEdge {
  src: string;
  dst: string;
  prop?: string;
  /** True for typed edges (direction matters for constraint inference). */
  directed?: boolean;
  /** True when the statement carries its own date qualifier. */
  dated?: boolean;
}

export type AnchorKind = 'start' | 'other' | 'end';

export interface Anchor {
  kind: AnchorKind;        // 'end' means end-anchored, visually flagged
  property: string;
  /** Astronomical year as a float (year 0 exists; 100.5 ≈ mid-year 100). */
  year: number;
  precision: number;
  /** Uncertainty extent implied by the precision, in years (§5.2.2). */
  spanYears: number;
  /** True when equally precise conflicting values existed (warning marker). */
  conflict: boolean;
}

export interface EventTick {
  property: string;
  year: number;
  precision: number;
  spanYears: number;
  /** Original Wikidata time string, for precision-faithful display. */
  timeValue?: string;
  sourceProperty?: string;
  sourceTarget?: string;
  kind: 'start' | 'end' | 'nested' | 'other';
}

export interface AnchorPolicy {
  /** Start-type properties in priority order (§5.2.1 step 1). */
  starts: string[];
  /** Fallback point-in-time properties (step 2). */
  others: string[];
  /** End-type properties, position at end date, flagged (step 3). */
  ends: string[];
}

export interface InferenceRules {
  /** Properties implying src begins before dst ends (e.g. P1542 cause of). */
  srcEarlier: string[];
  /** Properties implying dst begins before src ends (e.g. P155 follows). */
  dstEarlier: string[];
  /** Properties whose dateless statements are generic — excluded (§5.2.3). */
  nonspecific: string[];
}

export interface LayoutOptions {
  policy?: AnchorPolicy;
  /** Undated node strategy (§5.2.3). */
  undated?: 'margin' | 'infer';
  rules?: InferenceRules;
}

export interface PositionedEntity {
  id: string;
  anchor: Anchor | null;
  /** End anchor when the entity has both (renders as a lifespan bar). */
  endAnchor: Anchor | null;
  /** Feasible interval for undated nodes under 'infer' (may be half-open). */
  inferred: { min: number | null; max: number | null } | null;
  /** 'timeline' rows get a lane; 'margin' nodes are docked (§5.2.3). */
  region: 'timeline' | 'margin';
  lane: number;
  events: EventTick[];
}

export interface TemporalLayout {
  entities: PositionedEntity[];
  laneCount: number;
  /** Overall dated extent [minYear, maxYear], or null if nothing is dated. */
  extent: [number, number] | null;
}
