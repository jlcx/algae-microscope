/**
 * Zoomable time axis (§5.2.2): astronomical-year domain → pixel range, with
 * precision-aware tick generation (Ga/Ma/ka in deep time, years/months/days
 * elsewhere).
 */

import { formatYear } from './time.ts';

export interface Tick {
  year: number;
  label: string;
  major: boolean;
}

const STEP_MANTISSAS = [1, 2, 5];

/** Largest "nice" step ≤ target from the 1/2/5 · 10^k family, extended below
 * one year with month (1/12) and day (1/365) steps. */
function niceStep(target: number): number {
  if (target < 1) {
    if (target >= 1 / 12) return 1 / 12;
    return 1 / 365.2425;
  }
  const exp = Math.floor(Math.log10(target));
  let best = 10 ** exp;
  for (const m of STEP_MANTISSAS) {
    const step = m * 10 ** exp;
    if (step <= target) best = step;
  }
  return best;
}

export class TimeScale {
  domainMin: number;
  domainMax: number;
  rangeMin: number;
  rangeMax: number;

  constructor(domainMin: number, domainMax: number,
              rangeMin: number, rangeMax: number) {
    this.domainMin = domainMin;
    this.domainMax = domainMax;
    this.rangeMin = rangeMin;
    this.rangeMax = rangeMax;
  }

  get span(): number {
    return this.domainMax - this.domainMin;
  }

  toPx(year: number): number {
    return this.rangeMin
      + ((year - this.domainMin) / this.span) * (this.rangeMax - this.rangeMin);
  }

  toYear(px: number): number {
    return this.domainMin
      + ((px - this.rangeMin) / (this.rangeMax - this.rangeMin)) * this.span;
  }

  /** Zoom by `factor` keeping the year under `px` fixed. */
  zoom(factor: number, px: number): void {
    const pivot = this.toYear(px);
    this.domainMin = pivot + (this.domainMin - pivot) / factor;
    this.domainMax = pivot + (this.domainMax - pivot) / factor;
  }

  pan(dxPx: number): void {
    const dYear = (dxPx / (this.rangeMax - this.rangeMin)) * this.span;
    this.domainMin -= dYear;
    this.domainMax -= dYear;
  }

  /** Ticks for the current viewport, ~one per `pxPerTick` pixels. */
  ticks(pxPerTick = 90): Tick[] {
    const width = this.rangeMax - this.rangeMin;
    const count = Math.max(2, Math.floor(width / pxPerTick));
    const step = niceStep(this.span / count);
    const first = Math.ceil(this.domainMin / step) * step;
    const result: Tick[] = [];
    for (let year = first; year <= this.domainMax + step * 1e-9; year += step) {
      // snap away float error on multi-step accumulation
      const snapped = Math.abs(year) < step * 1e-6 ? 0 : year;
      result.push({
        year: snapped,
        label: formatYear(snapped, step),
        major: Math.abs(snapped / (step * 5)
          - Math.round(snapped / (step * 5))) < 1e-9,
      });
    }
    return result;
  }
}
