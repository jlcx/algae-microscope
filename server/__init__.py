"""algae-microscope server package: backends, neighborhood expansion, API."""

__version__ = "0.1.0"

# Version of the serialized neighborhood JSON schema (SPEC.md §6.2).
NEIGHBORHOOD_SCHEMA_VERSION = 1

# ms_* contract versions this build knows how to read (SPEC.md §1.2).
SUPPORTED_CONTRACT_VERSIONS = {1}
