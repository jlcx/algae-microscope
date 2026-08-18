/** Wire types mirroring the serialized neighborhood schema (SPEC.md §6.2)
 * and the /api/config payload. */

export interface DateClaim {
  property: string;
  time_value: string;
  precision: number;
  source_property: string;
  source_target: string;
}

export interface NNode {
  qid: string;
  label: string;
  wp_count: number | null;
  seed: boolean;
  hop: number;
  dates: DateClaim[];
}

export interface NEdge {
  id: string;
  kind: 'consensus' | 'typed';
  src: string;
  dst: string;
  prop?: string;
  wp_count?: number | null;
  langs?: string[] | null;
  effective_count?: number | null;
  wp_not_wd?: boolean | null;
  annotations?: Record<string, unknown>;
}

export interface Capabilities {
  witnesses: boolean;
  consensus: boolean;
  dates: boolean;
  bulk: boolean;
  contract_version: string | null;
}

export interface Neighborhood {
  schema: string;
  schema_version: number;
  seeds: string[];
  params: Record<string, unknown>;
  backend: { mode: string; capabilities: Capabilities };
  nodes: NNode[];
  edges: NEdge[];
  provenance: Record<string, unknown>;
}

export interface Delta {
  nodes: NNode[];
  edges: NEdge[];
  provenance: Record<string, unknown>;
}

export interface ClientConfig {
  witnesses: {
    clone_families: string[][];
    family_cap: number;
    weights: Record<string, number>;
  };
  temporal: { anchor_priority: string[]; undated: 'margin' | 'infer' };
  expansion: { default_hops: number; max_hops: number; default_budget: number };
  cg_rels: Record<string, string>;
  prop_categories: Record<string, string>;
}

export interface SearchHit {
  qid: string;
  label: string;
  description: string;
}

export interface RequestFilters {
  min_consensus?: number;
  props?: string | string[];
  edge_kinds?: string[];
  direction?: 'both' | 'out' | 'in';
}
