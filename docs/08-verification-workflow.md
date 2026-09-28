# Bhu-Drishti 3D — Verification & Authority Governance Workflow

## 1. Lifecycle State Machine
Cadastral records transition through governed states:

```
                  ┌─────────┐
                  │  DRAFT  │
                  └────┬────┘
                       │ Submitter uploads spatial evidence
                       ▼
                ┌─────────────┐
                │  SUBMITTED  │
                └──────┬──────┘
                       │ Automated ingestion & CRS reprojection
                       ▼
                ┌─────────────┐
                │  INGESTING  │
                └──────┬──────┘
                       │ AI extraction & volume generation
                       ▼
                ┌─────────────┐
                │  GENERATED  │
                └──────┬──────┘
                       │ Rules R001 to R016 evaluated
                       ▼
                ┌──────────────┐
                │  VALIDATION  │
                └──────┬───────┘
                       │ Discrepancies routed to queue
                       ▼
               ┌────────────────┐
               │  NEEDS_REVIEW  │
               └───────┬────────┘
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
  ┌───────────┐  ┌───────────┐  ┌───────────────────────┐
  │  APPROVE  │  │  REJECT   │  │ CORRECTION_REQUESTED  │
  └─────┬─────┘  └───────────┘  └───────────┬───────────┘
        │                                   │ Resubmission loop
        │ Signed via Ed25519                ▼
        │ & Committed to Hash Chain    ┌─────────────┐
        ▼                              │  RESUBMIT   │
  ┌───────────┐                        └─────────────┘
  │ OFFICIAL  │
  │ 3D RECORD │
  └───────────┘
```

---

## 2. Role-Based Access Control (RBAC) Permissions
1. **State Admin:**
   - Jurisdiction boundary oversight, statewide QA metrics, system parameters.
   - Read-only on local cases unless granted explicit multi-district override.
2. **District Verifier:**
   - Adjudicates cases within assigned district.
   - Inspects 3D twin, evidence provenance, and topology clashes.
   - Authority to **APPROVE**, **REJECT**, or **REQUEST CORRECTION**.
3. **Taluka Verifier:**
   - Field inspections, site notes, surveyor remarks.
4. **Builder:**
   - Submits architectural CAD, point clouds, drone surveys.
   - Monitors review progress and responds to correction requests.
5. **Citizen:**
   - Registers individual property units, views submission receipts.
6. **Public User:**
   - Scans public QR codes, inspects cryptographic proofs, downloads certificates.
   - Zero access to private citizen identifiers or loan amounts (DPDP compliance).
