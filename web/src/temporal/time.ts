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
  // sub-year: month labels
  const y = Math.floor(year);
  const monthIndex = Math.min(11, Math.floor((year - y) * 12));
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  if (unitSpan >= 1 / 12) return `${months[monthIndex]} ${y <= 0 ? `${1 - y} BCE` : y}`;
  const dayOfYear = Math.floor((year - y) * DAYS_IN_YEAR);
  return `${months[monthIndex]} d${dayOfYear} ${y}`;
}
