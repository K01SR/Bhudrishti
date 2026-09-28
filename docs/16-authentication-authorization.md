# Role-Based Access Control & DPDP Act 2023 Redaction

> **Canonical System Reference:** [Master Monograph Chapter 11](../docs/00-master-system-documentation.md#11-role-based-access-control--dpdp-act-2023-redaction)  
> **Source Files:** [`frontend/src/context/AppContext.tsx`](../frontend/src/context/AppContext.tsx), [`frontend/src/components/layout/AppShell.tsx`](../frontend/src/components/layout/AppShell.tsx)  
> **Tests:** [`tests/test_api_endpoints.py:test_property_detail_and_rights`](../tests/test_api_endpoints.py)

---

## 1. Sovereign Role Hierarchy
The platform establishes 6 distinct access personas:
1. `STATE_ADMIN`: State-wide governance, macro metrics, and district comparison consoles.
2. `DISTRICT_VERIFIER`: Statutory verification officer with approval and rollback powers.
3. `TALUKA_VERIFIER`: Field validation officer with spatial inspection tools.
4. `BUILDER`: Project applicant with submission tracking and CAD intake.
5. `CITIZEN`: Public property seeker with DPDP Act 2023 redacted records and objection filing.
6. `PUBLIC`: Anonymous public lookup with non-sensitive spatial verification.
