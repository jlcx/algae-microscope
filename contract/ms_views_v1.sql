-- algae-microscope query contract, version 1 (SPEC.md §1.2).
--
-- Mirrored from algae-farmer; apply to an ALGAE database to expose the
-- read-only view surface microscope consumes. Owned by algae-farmer and
-- versioned with the schema the views read — this copy exists so microscope
-- can print/apply the contract against a database that predates it.
--
-- Base schema reference: algae-farmer queries/db_commands.sql and
-- queries/migrate_witness_provenance.sql
-- (commit f1833232b653580ff2d115801920c6790724446a).
--
-- Note on witness columns: the post-migration wp_links table stores the
-- per-language witness set as `witnesses INT2[]`; the contract exposes it
-- under the name `langs`. On a pre-migration database (no witnesses column),
-- create ms_wp_links with `NULL::int2[] AS langs` instead — microscope
-- detects the NULL column and degrades to wp_count-only mode (§1.2).

CREATE OR REPLACE VIEW ms_meta AS
SELECT 1 AS ms_contract_version;

-- Consensus edges with per-language witness provenance
CREATE OR REPLACE VIEW ms_wp_links AS
SELECT src, dst, witnesses AS langs, wp_count
FROM wp_links;

-- Typed Wikidata edges
CREATE OR REPLACE VIEW ms_wd_links AS
SELECT src, dst, prop FROM wd_links;

-- Entity labels and coverage
CREATE OR REPLACE VIEW ms_entities AS
SELECT qid, best_label, wp_count FROM wd_entities;

-- Date claims (top-level and nested), for temporal layout
CREATE OR REPLACE VIEW ms_dates AS
SELECT qid, property, time_value, precision, source_property, source_target
FROM wd_dates;

-- Language dimension (append-only registry backing the int2[] witness arrays)
CREATE OR REPLACE VIEW ms_languages AS
SELECT id AS lang_id, code AS lang_code FROM languages;

-- Recommended supporting indexes. Not created here — index DDL on 10^8-10^9
-- row tables is the DBA's call and the builds take a while.
--
-- Interactive label search (§3.1); microscope's search fails fast with a
-- hint when it is absent:
--   CREATE INDEX idx_wd_entities_label
--       ON wd_entities (best_label text_pattern_ops);
--
-- Multi-hop expansion through hub entities (§3.2): fetching a hub's
-- consensus edges ordered by strength currently bitmap-scans all of them
-- (~minutes for frontiers containing e.g. countries). Composite indexes
-- would let per-node top-K reads replace the scan:
--   CREATE INDEX idx_wp_links_src_count ON wp_links (src, wp_count DESC);
--   CREATE INDEX idx_wp_links_dst_count ON wp_links (dst, wp_count DESC);
