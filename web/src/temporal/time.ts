/**
 * Wikidata time parsing and precision math (§5.2.2). The time value alone is
 * meaningless without its precision; both travel together everywhere here.
 */

const TIME_RE = /^([+-]\d+)-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)Z?$/;

export const GREGORIAN = 'http://www.wikidata.org/entity/Q1985727';
export const JULIAN = 'http://www.wikidata.org/entity/Q1985786';

const DAYS_IN_YEAR = 365.2425;

/**
 * Parse a Wikidata time string into an astronomical year float.
 *
 * Month/day 00 (unknown at the value's precision) count as mid-unit only via
 * precision spans, not here: 00 parses as the start of the unit. Julian
 * calendar values (pre-1583 where it matters) are shifted by the
 * Julian→Gregorian drift, which is far below every precision at which the
 * calendars are actually distinguishable on this axis except day precision.
 */
export function parseTimeValue(
  time: string,
  calendarmodel?: string,
): number | null {
  const match = TIME_RE.exec(time);
  if (!match) return null;
  const year = parseInt(match[1], 10);
  const month = parseInt(match[2], 10);
  const day = parseInt(match[3], 10);
  const hour = parseInt(match[4], 10);
  const minute = parseInt(match[5], 10);
  let frac = 0;
  if (month >= 1) frac += (month - 1) / 12;
  if (day >= 1) frac += (day - 1) / DAYS_IN_YEAR;
  frac += (hour + minute / 60) / (24 * DAYS_IN_YEAR);
  let result = year + frac;
  if (calendarmodel === JULIAN) {
    // Julian dates drift ~1 day per 128 years relative to proleptic
    // Gregorian; convert so day-precision values land on the right day.
    const centuries = Math.floor(year / 100);
    const driftDays = centuries - Math.floor(centuries / 4) - 2;
    result += driftDays / DAYS_IN_YEAR;
  }
  return result;
}

/** Interval implied by a Wikidata precision, in years (§5.2.2). */
export function precisionSpanYears(precision: number): number {
  switch (precision) {
    case 14: return 1 / (DAYS_IN_YEAR * 24 * 3600);
    case 13: return 1 / (DAYS_IN_YEAR * 24 * 60);
    case 12: return 1 / (DAYS_IN_YEAR * 24);
    case 11: return 1 / DAYS_IN_YEAR;
    case 10: return 1 / 12;
    case 9: return 1;
    case 8: return 10;
    case 7: return 100;
    case 6: return 1000;
    case 5: return 1e4;
    case 4: return 1e5;
    case 3: return 1e6;
    case 2: return 1e7;
    case 1: return 1e8;
    default: return 1e9;
  }
}

/**
 * Uncertainty extent of a value: [start, end] of the unit the precision
 * names. A precision-7 "century" value spans its century.
 */
export function precisionExtent(
  year: number,
  precision: number,
): [number, number] {
  const span = precisionSpanYears(precision);
  if (precision >= 9) {
    // year and finer: the parsed value is the start of its unit
    return [year, year + span];
  }
  const start = Math.floor(year / span) * span;
  return [start, start + span];
}

/** Human label for a year at a given axis scale (Ga/Ma/ka for deep time). */
export function formatYear(year: number, unitSpan: number): string {
  const abs = Math.abs(year);
  if (abs >= 1e9 || (unitSpan >= 1e8 && abs > 0)) {
    return `${(year / 1e9).toPrecision(3).replace(/\.?0+$/, '')} Ga`;
  }
  if (abs >= 1e6 || (unitSpan >= 1e5 && abs > 0)) {
    return `${(year / 1e6).toPrecision(3).replace(/\.?0+$/, '')} Ma`;
  }
  if (abs >= 2e4 || (unitSpan >= 1e4 && abs > 0)) {
    return `${(year / 1e3).toPrecision(3).replace(/\.?0+$/, '')} ka`;
  }
  const whole = Math.round(year);
  if (whole <= 0 && unitSpan >= 1) return `${1 - whole} BCE`;
  if (unitSpan >= 1) return `${whole}`;
  // sub-year: ISO-style labels. Invert the year-fraction encoding used by
  // parseTimeValue: (month-1)/12 dominates and the day term stays below
  // 1/12, so the month floor is exact and the remainder recovers the day.
  const y = Math.floor(year);
  const frac = year - y;
  const monthIndex = Math.min(11, Math.floor(frac * 12));
  const yearLabel = y > 0 ? String(y).padStart(4, '0') : String(y);
  const mm = String(monthIndex + 1).padStart(2, '0');
  if (unitSpan >= 1 / 12) return `${yearLabel}-${mm}`;
  const day = Math.round((frac - monthIndex / 12) * DAYS_IN_YEAR) + 1;
  return `${yearLabel}-${mm}-${String(Math.min(day, 31)).padStart(2, '0')}`;
}

const ORDINALS = ['th', 'st', 'nd', 'rd'];

function ordinal(n: number): string {
  const mod = n % 100;
  const suffix = (mod >= 11 && mod <= 13)
    ? 'th' : ORDINALS[n % 10] ?? 'th';
  return `${n}${suffix}`;
}

/**
 * Precision-faithful rendering of a raw Wikidata time string — no float
 * round trip, so day-precision values come out exactly as stored:
 * p11 → "2009-11-13", p10 → "2009-11", p9 → "1952" / "44 BCE",
 * p8 → "1950s", p7 → "19th century", p6 → "2nd millennium",
 * coarser → Ga/Ma/ka via formatYear.
 */
export function formatDateValue(time: string, precision: number,
                                calendarmodel?: string): string {
  const match = TIME_RE.exec(time);
  if (!match) return time;
  const year = parseInt(match[1], 10);
  if (precision >= 11) {
    const yearLabel = year > 0 ? String(year).padStart(4, '0') : String(year);
    let out = `${yearLabel}-${match[2]}-${match[3]}`;
    if (precision >= 12) out += ` ${match[4]}:${match[5]}`;
    return out;
  }
  if (precision === 10) {
    const yearLabel = year > 0 ? String(year).padStart(4, '0') : String(year);
    return `${yearLabel}-${match[2]}`;
  }
  if (precision === 9) return year <= 0 ? `${1 - year} BCE` : `${year}`;
  const parsed = parseTimeValue(time, calendarmodel) ?? year;
  const span = precisionSpanYears(precision);
  const start = Math.floor(parsed / span) * span;
  if (precision === 8) return `${start}s`;
  if (precision === 7) {
    return start >= 0 ? `${ordinal(start / 100 + 1)} century`
      : `${ordinal(-(start + 100) / 100 + 1)} century BCE`;
  }
  if (precision === 6) {
    return start >= 0 ? `${ordinal(start / 1000 + 1)} millennium`
      : `${ordinal(-(start + 1000) / 1000 + 1)} millennium BCE`;
  }
  return formatYear(parsed, span);
}
