"""Wikidata property constants shared with algae-farmer (SPEC.md §2.4).

VENDORED from algae-farmer commit f1833232b653580f (src/constants.rs and
scripts/back_edges.py). algae-farmer uses these at extraction time; microscope
uses them at display/layout time. If the two drift, re-vendor from
algae-farmer and update the commit hash above; promote to a shared package
only if drift becomes a recurring problem.
"""

# Causal-graph relationship set with display labels. This is the extended
# back_edges.py CG_RELS (itself from cg-data-scripts wd_constants.cg_rels,
# P2860 "cites" still excluded for volume). All stored in claim direction.
CG_RELS = {
    'P737': 'influenced by',
    'P941': 'inspired by',
    'P2675': 'reply to',
    'P144': 'based on',
    'P828': 'has cause',
    'P1542': 'cause of',
    'P1478': 'has immediate cause',
    'P1536': 'immediate cause of',
    'P1479': 'has contributing factor',
    'P1537': 'contributing factor of',
    'P22': 'father',
    'P25': 'mother',
    'P40': 'child',
    'P184': 'doctoral advisor',
    'P185': 'doctoral student',
    'P1066': 'student of',
    'P802': 'student',
    'P807': 'separated from',
    'P112': 'founded by',
    'P170': 'creator',
    'P50': 'author',
    'P61': 'discoverer or inventor',
    'P86': 'composer',
    'P87': 'librettist',
    'P178': 'developer',
    'P287': 'designed by',
    'P943': 'programmer',
    'P193': 'main building contractor',
    'P676': 'lyrics by',
    'P175': 'performer',
    'P84': 'architect',
    'P110': 'illustrator',
    'P1779': 'possible creator',
    'P5191': 'derived from',
    'P3448': 'stepparent',
    'P156': 'followed by',
    'P155': 'follows',
    'P1366': 'replaced by',
    'P1365': 'replaces',
    'P167': 'structure replaced by',
    'P710': 'participant',
    'P1344': 'participant of',
    'P162': 'producer',
    'P272': 'production company',
    'P2515': 'costume designer',
    'P4805': 'make-up artist',
    'P2554': 'production designer',
    'P1040': 'film editor',
    'P3092': 'film crew member',
    'P3342': 'significant person',
    'P344': 'director of photography',
    'P1431': 'executive producer',
    'P161': 'cast member',
    'P58': 'screenwriter',
    'P57': 'director',
    'P138': 'named after',
    'P800': 'notable work',
    'P3919': 'contributed to creative work',
    'P6338': 'colorist',
    'P176': 'manufacturer',
    'P8371': 'references work, tradition or theory',
    'P4969': 'derivative work',
    'P6166': 'quotes work',
    'P5707': 'samples from work',
    'P1625': 'has melody',
    'P6439': 'has lyrics',
    'P1877': 'after a work by',
    'P5059': 'modified version of',
    'P629': 'edition or translation of',
    'P9810': 'remix of',
}

# Property-class groupings for edge coloring (§5.1), following the section
# comments in constants.rs cg_rels() extended to cover the full CG_RELS set.
CG_REL_CATEGORIES = {
    'influence': ['P737', 'P941', 'P144', 'P5191', 'P2675', 'P8371', 'P6166',
                  'P5707', 'P1625', 'P6439', 'P1877', 'P5059', 'P629',
                  'P9810', 'P4969'],
    'causation': ['P828', 'P1542', 'P1478', 'P1536', 'P1479', 'P1537'],
    'kinship': ['P22', 'P25', 'P40', 'P3448'],
    'mentorship': ['P184', 'P185', 'P1066', 'P802', 'P807'],
    'creation': ['P112', 'P170', 'P50', 'P61', 'P86', 'P87', 'P178', 'P287',
                 'P943', 'P193', 'P676', 'P84', 'P110', 'P1779', 'P3919',
                 'P176'],
    'succession': ['P155', 'P156', 'P1365', 'P1366', 'P167'],
    'production': ['P57', 'P58', 'P161', 'P162', 'P272', 'P344', 'P1040',
                   'P1431', 'P2515', 'P2554', 'P3092', 'P4805', 'P6338',
                   'P175'],
    'other': ['P138', 'P800', 'P710', 'P1344', 'P3342'],
}

CATEGORY_BY_PROP = {
    prop: cat for cat, props in CG_REL_CATEGORIES.items() for prop in props
}

# Date-property classes (constants.rs starts()/ends()/others()).
STARTS = {
    'P580',   # start time
    'P571',   # inception
    'P569',   # date of birth
    'P575',   # time of discovery or invention
    'P577',   # publication date
    'P729',   # service entry
    'P1191',  # first performance
    'P1319',  # earliest date
    'P6949',  # announcement date
    'P2031',  # work period (start)
    'P3999',  # date of official opening
    'P1619',  # date of official opening (alt)
}

ENDS = {
    'P582',   # end time
    'P576',   # dissolved, abolished or demolished date
    'P570',   # date of death
    'P2669',  # discontinued date
    'P730',   # service retirement
    'P3999',  # date of official closing
    'P2032',  # work period (end)
    'P1326',  # latest date
    'P746',   # date of disappearance
}

OTHERS = {'P585', 'P1317'}  # point in time, floruit

# Default anchor priority within STARTS (§5.2.1); config anchor_priority is
# prepended to this.
STARTS_DEFAULT_ORDER = [
    'P569', 'P571', 'P580', 'P577', 'P575', 'P1191', 'P729', 'P2031',
    'P3999', 'P1619', 'P6949', 'P1319',
]

_EXTRA_TIMES = {
    'P585', 'P1317', 'P813', 'P1326', 'P1319', 'P2913', 'P3893', 'P2960',
    'P606', 'P607', 'P1636', 'P2754', 'P2755', 'P2756', 'P7124', 'P7125',
    'P837', 'P1734', 'P4602', 'P1249', 'P6257', 'P1619', 'P3999', 'P6949',
    'P8556', 'P8557', 'P580', 'P582', 'P571', 'P576', 'P569', 'P570',
    'P577', 'P575', 'P729', 'P730', 'P1191', 'P2031', 'P2032', 'P2669',
    'P746', 'P7588', 'P7589', 'P2610', 'P523', 'P524', 'P2894', 'P2895',
    'P3415', 'P556', 'P748', 'P749', 'P859', 'P1389', 'P7104', 'P7103',
    'P6555', 'P6556', 'P4733', 'P4734', 'P9714', 'P9715', 'P2285', 'P2286',
    'P4282', 'P4283', 'P6207', 'P6208', 'P7506', 'P7507', 'P7584', 'P7585',
}

ALL_TIMES = STARTS | ENDS | OTHERS | _EXTRA_TIMES

# Properties that may carry date qualifiers nested inside non-date claims.
NESTED_TIME_RELS = {
    'P348',   # software version identifier
    'P106',   # occupation
    'P108',   # employer
    'P69',    # educated at
    'P26',    # spouse
    'P449',   # original network
    'P793',   # significant event
    'P1891',  # signatory
}

TIMES_PLUS_NESTED = ALL_TIMES | NESTED_TIME_RELS

# Properties whose dateless statements are probably generic/non-specific;
# excluded from temporal constraint inference (§5.2.3).
LIKELY_NONSPECIFIC = {'P828', 'P1542', 'P1478', 'P1536', 'P1479', 'P1537'}

_ORIGINAL_INVERSES = [
    ('P22', 'P40'), ('P25', 'P40'), ('P40', 'P22'),
    ('P184', 'P185'), ('P185', 'P184'),
    ('P1066', 'P802'), ('P802', 'P1066'),
    ('P155', 'P156'), ('P156', 'P155'),
    ('P1365', 'P1366'), ('P1366', 'P1365'),
    ('P828', 'P1542'), ('P1542', 'P828'),
    ('P1478', 'P1536'), ('P1536', 'P1478'),
    ('P1479', 'P1537'), ('P1537', 'P1479'),
    ('P710', 'P1344'), ('P1344', 'P710'),
]

_SYNTHETIC_INVERSES = [
    'P50', 'P57', 'P58', 'P61', 'P86', 'P112', 'P138', 'P144', 'P161',
    'P162', 'P170', 'P175', 'P176', 'P178', 'P272', 'P279', 'P287',
    'P344', 'P737', 'P800', 'P941', 'P1040', 'P1431', 'P2515', 'P2554',
    'P3092', 'P3448', 'P5191', 'P6338',
]


def combined_inverses() -> dict[str, str]:
    """Inverse property map: Wikidata-defined pairs plus synthetic 'Pxi'
    inverses for properties without official ones."""
    m = dict(_ORIGINAL_INVERSES)
    for p in _SYNTHETIC_INVERSES:
        m[p] = p + 'i'
        m[p + 'i'] = p
    return m


COMBINED_INVERSES = combined_inverses()

# Short fallback chain for human-readable labels (constants.rs LANG_ORDER).
LANG_ORDER = [
    'en', 'de', 'fr', 'es', 'it', 'pl', 'pt', 'nl', 'sv', 'no', 'fi', 'ro',
]
