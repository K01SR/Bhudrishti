# Security Architecture, Threat Matrix & Hardening

> **Canonical System Reference:** [Master Monograph Chapter 15](../docs/00-master-system-documentation.md#15-security-architecture-threat-matrix--hardening)  
> **Source Files:** [`backend/app/core/blockchain.py`](../backend/app/core/blockchain.py), [`backend/app/main.py`](../backend/app/main.py)  
> **Tests:** [`tests/test_cryptography.py`](../tests/test_cryptography.py)

---

## 1. Defense-in-Depth Security Matrix
* **Cryptographic Tamper-Evidence:** Ed25519 digital signatures and SHA-256 Merkle proofs.
* **SQL Injection Immunity:** 100% parameterized SQLAlchemy and PostGIS spatial queries.
* **DPDP Act 2023 Privacy:** Automated field-level masking of sensitive owner identifiers, bank accounts, and mortgage values for public and citizen roles.
* **CORS & Input Sanitization:** Strict origin filtering, Pydantic v2 input boundary validation, and zero unhandled exceptions.
