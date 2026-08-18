import test from 'node:test';
import assert from 'node:assert/strict';

import {
  parseTimeValue, precisionExtent, formatYear, JULIAN,
} from './time.ts';
import {
  DEFAULT_POLICY, withPriority, selectAnchor, secondaryEvents,
} from './anchor.ts';
import { inferInterval } from './infer.ts';
import { TimeScale } from './scale.ts';
import { layoutTemporal } from './layout.ts';
import type { Anchor, TemporalDateClaim } from './types.ts';

const claim = (
  property: string, time: string, precision: number,
  source_property = '', source_target = '',
): TemporalDateClaim => ({
  property, time_value: time, precision, source_property, source_target,
});

test('parseTimeValue basic and BCE', () => {
  assert.equal(parseTimeValue('+1952-01-01T00:00:00Z'), 1952);
  const mid = parseTimeValue('+1952-07-01T00:00:00Z')!;
  assert.ok(mid > 1952.4 && mid < 1952.6);
  assert.equal(parseTimeValue('-0044-01-01T00:00:00Z'), -44);
  assert.equal(parseTimeValue('+1000000000-00-00T00:00:00Z'), 1e9);
  assert.equal(parseTimeValue('garbage'), null);
});

test('julian calendar shifts day-precision values', () => {
  const gregorian = parseTimeValue('+1000-03-01T00:00:00Z')!;
  const julian = parseTimeValue('+1000-03-01T00:00:00Z', JULIAN)!;
  assert.ok(Math.abs((julian - gregorian) * 365.2425 - 6) < 1.5); // ~6 days in year 1000
});

test('precisionExtent spans the named unit', () => {
  const [start, end] = precisionExtent(1952, 9);
  assert.equal(start, 1952);
  assert.equal(end, 1953);
  const [cStart, cEnd] = precisionExtent(1877, 7); // "19th century"
  assert.equal(cStart, 1800);
  assert.equal(cEnd, 1900);
});

test('formatYear deep time and BCE', () => {
  assert.equal(formatYear(-2.5e9, 1e9), '-2.5 Ga');
  assert.equal(formatYear(-65e6, 1e6), '-65 Ma');
  assert.equal(formatYear(-9999, 1), '10000 BCE');
  assert.equal(formatYear(1969, 1), '1969');
});

test('anchor policy: starts before others before ends', () => {
  const dates = [
    claim('P570', '+1980-01-01T00:00:00Z', 9),  // death (end)
    claim('P585', '+1970-01-01T00:00:00Z', 9),  // point in time (other)
    claim('P569', '+1900-01-01T00:00:00Z', 9),  // birth (start)
  ];
  const anchor = selectAnchor(dates)!;
  assert.equal(anchor.property, 'P569');
  assert.equal(anchor.kind, 'start');

  const noStart = selectAnchor(dates.slice(0, 2))!;
  assert.equal(noStart.property, 'P585');
  const endOnly = selectAnchor(dates.slice(0, 1))!;
  assert.equal(endOnly.kind, 'end'); // end-anchored, visually flagged
});

test('nested claims never anchor the entity', () => {
  assert.equal(
    selectAnchor([claim('P580', '+1960-01-01T00:00:00Z', 9, 'P108', 'Q1')]),
    null);
});

test('conflicting same-precision values flag a warning', () => {
  const anchor = selectAnchor([
    claim('P571', '+1950-01-01T00:00:00Z', 9),
    claim('P571', '+1955-01-01T00:00:00Z', 9),
    claim('P571', '+1950-00-00T00:00:00Z', 7),
  ])!;
  assert.equal(anchor.conflict, true);
  assert.equal(anchor.precision, 9); // highest precision wins

  const resolved = selectAnchor([
    claim('P571', '+1950-01-01T00:00:00Z', 9),
    claim('P571', '+1950-00-00T00:00:00Z', 7),
  ])!;
  assert.equal(resolved.conflict, false);
});

test('withPriority prepends configured order', () => {
  const policy = withPriority(DEFAULT_POLICY, ['P571', 'P569']);
  const anchor = selectAnchor([
    claim('P569', '+1900-01-01T00:00:00Z', 9),
    claim('P571', '+1950-01-01T00:00:00Z', 9),
  ], policy)!;
  assert.equal(anchor.property, 'P571');
});

test('secondaryEvents classifies ticks', () => {
  const events = secondaryEvents([
    claim('P569', '+1900-01-01T00:00:00Z', 9),
    claim('P570', '+1980-01-01T00:00:00Z', 9),
    claim('P580', '+1960-01-01T00:00:00Z', 9, 'P108', 'Q7'),
  ]);
  assert.deepEqual(events.map(e => e.kind), ['start', 'nested', 'end']);
  assert.equal(events[1].sourceProperty, 'P108');
});

test('inferInterval bounds from succession neighbors', () => {
  const anchors = new Map<string, Anchor>([
    ['Q1', { kind: 'start', property: 'P571', year: 1900, precision: 9,
             spanYears: 1, conflict: false }],
    ['Q2', { kind: 'start', property: 'P571', year: 1950, precision: 9,
             spanYears: 1, conflict: false }],
  ]);
  // U follows Q1 (P155: dst earlier -> U after 1900),
  // U followed by Q2 (P156: src earlier -> U before 1950)
  const interval = inferInterval('U', [
    { src: 'U', dst: 'Q1', prop: 'P155', directed: true },
    { src: 'U', dst: 'Q2', prop: 'P156', directed: true },
  ], anchors)!;
  assert.equal(interval.min, 1900);
  assert.equal(interval.max, 1950);
});

test('inferInterval skips dateless nonspecific causal claims', () => {
  const anchors = new Map<string, Anchor>([
    ['Q1', { kind: 'start', property: 'P571', year: 1900, precision: 9,
             spanYears: 1, conflict: false }]]);
  assert.equal(inferInterval('U', [
    { src: 'U', dst: 'Q1', prop: 'P828', directed: true },
  ], anchors), null);
  assert.notEqual(inferInterval('U', [
    { src: 'U', dst: 'Q1', prop: 'P828', directed: true, dated: true },
  ], anchors), null);
});

test('TimeScale roundtrip, zoom, ticks', () => {
  const scale = new TimeScale(1900, 2000, 0, 1000);
  assert.equal(scale.toPx(1950), 500);
  assert.equal(scale.toYear(500), 1950);
  scale.zoom(2, 500);
  assert.equal(Math.round(scale.domainMin), 1925);
  assert.equal(Math.round(scale.domainMax), 1975);
  const ticks = scale.ticks();
  assert.ok(ticks.length >= 3);
  assert.ok(ticks.every(t => t.year >= scale.domainMin - 1e-9
    && t.year <= scale.domainMax + 1e-9));
});

test('layoutTemporal separates concurrent entities into lanes', () => {
  const entities = [
    { id: 'A', dates: [claim('P569', '+1900-01-01T00:00:00Z', 9),
                       claim('P570', '+1980-01-01T00:00:00Z', 9)] },
    { id: 'B', dates: [claim('P569', '+1910-01-01T00:00:00Z', 9),
                       claim('P570', '+1990-01-01T00:00:00Z', 9)] },
    { id: 'C', dates: [claim('P569', '+2000-01-01T00:00:00Z', 9)] },
    { id: 'U', dates: [] },
  ];
  const layout = layoutTemporal(entities, [], { undated: 'margin' });
  const byId = new Map(layout.entities.map(e => [e.id, e]));
  assert.notEqual(byId.get('A')!.lane, byId.get('B')!.lane); // concurrent
  assert.equal(byId.get('U')!.region, 'margin');
  assert.ok(layout.extent![0] <= 1900);
});

test('layoutTemporal infer mode places constrained undated nodes', () => {
  const entities = [
    { id: 'Q1', dates: [claim('P571', '+1900-01-01T00:00:00Z', 9)] },
    { id: 'U', dates: [] },
  ];
  const layout = layoutTemporal(entities,
    [{ src: 'U', dst: 'Q1', prop: 'P155', directed: true }],
    { undated: 'infer' });
  const u = layout.entities.find(e => e.id === 'U')!;
  assert.equal(u.region, 'timeline');
  assert.equal(u.inferred!.min, 1900);
});
