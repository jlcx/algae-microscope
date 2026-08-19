import json
import xml.etree.ElementTree as ET

from cli.export import format_date_value, to_dot, to_graphml, to_json, to_text
from server.neighborhood import WitnessWeights, expand

WEIGHTS = WitnessWeights(families=[["ceb", "war", "sv", "vi"]])


def _neighborhood(fixture_backend):
    return expand(fixture_backend, ["Q1"], hops=1, budget=100, weights=WEIGHTS)


def test_text(fixture_backend):
    text = to_text(_neighborhood(fixture_backend))
    assert "Alpha" in text
    assert "WP-not-WD" in text
    assert "P50 (author)" in text


def test_json_roundtrip(fixture_backend):
    data = json.loads(to_json(_neighborhood(fixture_backend)))
    assert data["schema_version"] == 1


def test_graphml_is_valid_xml(fixture_backend):
    xml = to_graphml(_neighborhood(fixture_backend))
    root = ET.fromstring(xml)
    ns = "{http://graphml.graphdrawing.org/xmlns}"
    nodes = root.findall(f"{ns}graph/{ns}node")
    edges = root.findall(f"{ns}graph/{ns}edge")
    assert len(nodes) == 4
    assert len(edges) >= 4


def test_format_date_value():
    assert format_date_value("+2009-11-13T00:00:00Z", 11) == "2009-11-13"
    assert format_date_value("+2009-11-00T00:00:00Z", 10) == "2009-11"
    assert format_date_value("+1952-03-11T00:00:00Z", 9) == "1952"
    assert format_date_value("-0043-00-00T00:00:00Z", 9) == "44 BCE"
    assert format_date_value("+1954-00-00T00:00:00Z", 8) == "1950s"
    assert format_date_value("+1877-00-00T00:00:00Z", 7) == "19th century"
    assert format_date_value("-0450-00-00T00:00:00Z", 7) == "5th century BCE"
    assert format_date_value("+1500-00-00T00:00:00Z", 6) == "2nd millennium"
    assert format_date_value("garbage", 9) == "garbage"


def test_dot(fixture_backend):
    dot = to_dot(_neighborhood(fixture_backend))
    assert dot.startswith("digraph")
    assert '"Q1" -> "Q2"' in dot
    assert "color=red" in dot  # wp_not_wd highlight
