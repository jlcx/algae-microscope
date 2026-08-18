/** Public surface of the separable temporal layout module (§5.2). */

export * from './types.ts';
export {
  parseTimeValue, precisionSpanYears, precisionExtent, formatYear,
  GREGORIAN, JULIAN,
} from './time.ts';
export {
  DEFAULT_POLICY, withPriority, selectAnchor, selectEndAnchor,
  secondaryEvents,
} from './anchor.ts';
export { DEFAULT_RULES, inferInterval } from './infer.ts';
export { TimeScale, type Tick } from './scale.ts';
export { layoutTemporal } from './layout.ts';
