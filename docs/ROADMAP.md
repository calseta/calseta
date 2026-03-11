# Calseta — Roadmap

Future enhancements tracked here. Not committed to a timeline — prioritized as capacity allows.

---

## UI Enhancements

### MITRE ATT&CK Searchable Multi-Select
- Replace freetext chip inputs for tactics, techniques, and sub-techniques with searchable multi-select dropdowns
- Populate from the full MITRE ATT&CK catalog (Enterprise matrix)
- Sub-techniques scoped to their parent technique (e.g. T1059.001 only appears under T1059)
- Applies to: detection rule create modal, detection rule edit modal
- Prerequisite: decide whether to bundle the ATT&CK catalog as static JSON or fetch from MITRE's STIX/TAXII endpoint
