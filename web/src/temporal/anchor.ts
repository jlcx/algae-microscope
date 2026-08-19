/**
 * Anchor date selection (§5.2.1): a date policy picks the anchor used for
 * positioning from an entity's many date claims.
 */

import type {
  Anchor, AnchorKind, AnchorPolicy, EventTick, TemporalDateClaim,
} from './types.ts';
import { parseTimeValue, precisionSpanYears } from './time.ts';

/** Default policy mirroring the ALGAE starts/others/ends property classes. */
export const DEFAULT_POLICY: AnchorPolicy = {
  starts: ['P569', 'P571', 'P580', 'P577', 'P575', 'P1191', 'P729', 'P2031',
           'P3999', 'P1619', 'P6949', 'P1319'],
  others: ['P585', 'P1317'],
  ends: ['P570', 'P582', 'P576', 'P730', 'P746', 'P2032', 'P2669', 'P3999',
         'P1326'],
};

/** Prepend a configured priority list to a policy's starts order (§8). */
export function withPriority(
  policy: AnchorPolicy,
  priority: string[],
): AnchorPolicy {
  const starts = [...priority, ...policy.starts.filter(p => !priority.includes(p))];
  return { ...policy, starts };
}

interface ParsedClaim {
  property: string;
  year: number;
  precision: number;
}

function topLevelClaims(dates: TemporalDateClaim[]): ParsedClaim[] {
  const parsed: ParsedClaim[] = [];
  for (const claim of dates) {
    // Nested date claims date a relationship, not the entity (§5.2.1).
    if (claim.source_property) continue;
    const year = parseTimeValue(claim.time_value, claim.calendarmodel);
    if (year === null) continue;
    parsed.push({ property: claim.property, year, precision: claim.precision });
  }
  return parsed;
}

/**
 * Resolve multiple values of one property: highest precision wins; distinct
 * surviving values at that precision flag a conflict (warning marker).
 */
function resolveProperty(claims: ParsedClaim[]): {
  year: number; precision: number; conflict: boolean;
} {
  const best = Math.max(...claims.map(c => c.precision));
  const atBest = claims.filter(c => c.precision === best);
  const years = [...new Set(atBest.map(c => c.year))];
  return { year: years[0], precision: best, conflict: years.length > 1 };
}

function pickFrom(
  claims: ParsedClaim[],
  properties: string[],
  kind: AnchorKind,
): Anchor | null {
  for (const property of properties) {
    const matching = claims.filter(c => c.property === property);
    if (!matching.length) continue;
    const { year, precision, conflict } = resolveProperty(matching);
    return {
      kind, property, year, precision,
      spanYears: precisionSpanYears(precision), conflict,
    };
  }
  return null;
}

/** §5.2.1 policy: starts, else others, else ends (flagged), else undated. */
export function selectAnchor(
  dates: TemporalDateClaim[],
  policy: AnchorPolicy = DEFAULT_POLICY,
): Anchor | null {
  const claims = topLevelClaims(dates);
  if (!claims.length) return null;
  return pickFrom(claims, policy.starts, 'start')
    ?? pickFrom(claims, policy.others, 'other')
    ?? pickFrom(claims, [...policy.ends], 'end');
}

/**
 * End anchor for lifespan bars (§5.2.4): the highest-priority end property,
 * only meaningful when a start/other anchor exists.
 */
export function selectEndAnchor(
  dates: TemporalDateClaim[],
  policy: AnchorPolicy = DEFAULT_POLICY,
): Anchor | null {
  return pickFrom(topLevelClaims(dates), policy.ends, 'end');
}

/**
 * Secondary date events along an entity's row (§5.2.4): end dates, nested
 * qualifier dates, and other dated claims.
 */
export function secondaryEvents(
  dates: TemporalDateClaim[],
  policy: AnchorPolicy = DEFAULT_POLICY,
): EventTick[] {
  const events: EventTick[] = [];
  for (const claim of dates) {
    const year = parseTimeValue(claim.time_value, claim.calendarmodel);
    if (year === null) continue;
    let kind: EventTick['kind'];
    if (claim.source_property) kind = 'nested';
    else if (policy.ends.includes(claim.property)) kind = 'end';
    else if (policy.starts.includes(claim.property)) kind = 'start';
    else kind = 'other';
    events.push({
      property: claim.property, year, precision: claim.precision,
      spanYears: precisionSpanYears(claim.precision),
      timeValue: claim.time_value,
      sourceProperty: claim.source_property || undefined,
      sourceTarget: claim.source_target || undefined,
      kind,
    });
  }
  return events.sort((a, b) => a.year - b.year);
}
