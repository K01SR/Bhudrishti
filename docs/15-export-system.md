# Interoperability Engine & Multi-Tier Vector Export Suite

> **Canonical System Reference:** [Master Monograph Chapter 9](../docs/00-master-system-documentation.md#9-interoperability-engine--multi-tier-vector-export-suite)  
> **Source Files:** [`backend/app/api/v1/exports.py`](../backend/app/api/v1/exports.py), [`backend/app/id_engine/latex_pdf_generator.py`](../backend/app/id_engine/latex_pdf_generator.py)  
> **Tests:** [`tests/test_api_endpoints.py:test_dynamic_property_card_pdf_and_latex`](../tests/test_api_endpoints.py)

---

## 1. Supported Export Formats
* **Official Form 3D Property Card PDF (`/api/v1/exports/pdf/property-card/{ulpin}`):** 4-page vector PDF generated via ReportLab with State Seal, ULPIN badge, strata unit schedule, and verification QR code.
* **OGC CityJSON 1.1/2.0 (`/api/v1/exports/cityjson`):** International 3D GIS exchange format with LOD 2.2 building and unit semantics.
* **LaTeX Technical Monograph (`/api/v1/exports/latex/property-card/{ulpin}`):** Formal academic-grade LaTeX `.tex` source code adhering to RGU Thesis Standards.
* **Cadastral Register Excel Workbook (`/api/v1/exports/excel/cadastre`):** Multi-sheet workbook with units registry and verified blockchain audit log.
