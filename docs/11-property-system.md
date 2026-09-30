# Cadastral Data Resolution & Dynamic Property Synthesis

> **Canonical System Reference:** [Master Monograph Chapter 8](../docs/00-master-system-documentation.md#8-cadastral-data-resolution--dynamic-property-synthesis)  
> **Source Files:** [`backend/app/api/v1/exports.py`](../backend/app/api/v1/exports.py), [`backend/app/api/v1/parcels.py`](../backend/app/api/v1/parcels.py)  
> **Tests:** [`tests/test_api_endpoints.py:test_dynamic_property_card_pdf_and_latex`](../tests/test_api_endpoints.py)

---

## 1. The 4-Tier Resolution Hierarchy

To guarantee 100% uptime and prevent unhandled 404 errors during arbitrary property lookups, the platform employs a 4-tier resolution engine:
1. **Tier 1:** Hero Property B-17 (`12345678901234`) with full 21-unit legal strata and audit records.
2. **Tier 2:** Precinct Multi-Building Twins (`B-01` through `B-12`) preserving FSI, typology, and massing.
3. **Tier 3:** Persisted PostGIS Database (`NationalTwin` / `NationalParcel`).
4. **Tier 4:** Dynamic On-Demand Synthesis deriving compliant 6-floor envelopes, unit strata, CTS survey numbers, and official PDFs for any arbitrary identifier.
