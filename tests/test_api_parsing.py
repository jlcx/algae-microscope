"""Offline tests of the API-only backend's entity JSON parsing, which must
mirror algae-farmer wd_preproc extraction rules (SPEC.md §2.3)."""

from server.backends.api_only import (best_label, extract_dates,
                                      extract_typed_edges, wp_count)

ENTITY = {
    "id": "Q42",
    "lastrevid": 12345,
    "labels": {
        "mul": {"value": "Neutral Name"},
        "en": {"value": "English Label"},
        "de": {"value": "Deutsches Label"},
    },
    "sitelinks": {
        "enwiki": {"title": "English Title"},
        "dewiki": {"title": "Deutscher Titel"},
        "cebwiki": {"title": "Cebuano"},
        "enwikiquote": {"title": "Quote"},        # excluded
        "commonswiki": {"title": "Commons"},      # excluded
        "wikidatawiki": {"title": "WD"},          # excluded
        "specieswiki": {"title": "Species"},      # excluded
    },
    "claims": {
        "P50": [{  # wikibase-item mainsnak -> typed edge
            "mainsnak": {"datatype": "wikibase-item", "snaktype": "value",
                         "datavalue": {"value": {"id": "Q100"}}},
        }],
        "P569": [{  # date property -> top-level date claim
            "mainsnak": {"datatype": "time", "snaktype": "value",
                         "datavalue": {"value": {
                             "time": "+1952-03-11T00:00:00Z",
                             "precision": 11}}},
        }],
        "P108": [{  # nested date qualifier on an item claim
            "mainsnak": {"datatype": "wikibase-item", "snaktype": "value",
                         "datavalue": {"value": {"id": "Q200"}}},
            "qualifiers": {
                "P580": [{"datatype": "time",
                          "datavalue": {"value": {
                              "time": "+1980-00-00T00:00:00Z",
                              "precision": 9}}}],
                "P1545": [{"datatype": "string",
                           "datavalue": {"value": "1"}}],
            },
        }],
        "P1082": [{  # quantity claim: no edge, no date
            "mainsnak": {"datatype": "quantity", "snaktype": "value",
                         "datavalue": {"value": {"amount": "+5"}}},
        }],
        "P26": [{  # somevalue snak: no target id -> no edge
            "mainsnak": {"datatype": "wikibase-item", "snaktype": "somevalue"},
        }],
    },
}


def test_best_label_prefers_sitelink_title():
    assert best_label(ENTITY) == "English Title"


def test_best_label_falls_back_to_mul_then_labels():
    entity = {"id": "Q1", "labels": {"mul": {"value": "MulName"}}}
    assert best_label(entity) == "MulName"
    entity = {"id": "Q1", "labels": {"de": {"value": "NurDeutsch"}}}
    assert best_label(entity) == "NurDeutsch"
    assert best_label({"id": "Q1"}) == "Q1"


def test_wp_count_filters_non_wikipedia_sitelinks():
    assert wp_count(ENTITY) == 3  # en, de, ceb


def test_typed_edges_from_mainsnaks_and_qualifiers():
    edges = {(e.src, e.dst, e.prop) for e in extract_typed_edges(ENTITY)}
    assert ("Q42", "Q100", "P50") in edges
    assert ("Q42", "Q200", "P108") in edges   # item mainsnak of nested claim
    assert not any(prop == "P26" for _, _, prop in edges)  # somevalue skipped


def test_dates_top_level_and_nested():
    dates = extract_dates(ENTITY)
    top = [d for d in dates if not d.source_property]
    nested = [d for d in dates if d.source_property]
    assert len(top) == 1
    assert top[0].property == "P569" and top[0].precision == 11
    assert len(nested) == 1
    assert nested[0].property == "P580"
    assert nested[0].source_property == "P108"
    assert nested[0].source_target == "Q200"


def test_extreme_time_values_rejected():
    entity = {
        "id": "Q1",
        "claims": {"P569": [{
            "mainsnak": {"datatype": "time", "snaktype": "value",
                         "datavalue": {"value": {
                             "time": "+" + "9" * 40 + "-00-00T00:00:00Z",
                             "precision": 0}}},
        }]},
    }
    assert extract_dates(entity) == []
