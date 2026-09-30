# Bhu-Drishti 3D — Security & Privacy Architecture

## 1. Asymmetric Digital Signatures (Ed25519)
When an authorized cadastral officer approves a property record:
1. The property payload is serialized into deterministic canonical JSON (sorted keys, compact whitespace).
2. A 256-bit cryptographic digest is generated via SHA-256: $\text{Fingerprint} = \text{SHA256}(\text{CanonicalJSON})$.
3. The digest is signed using the state verifier's private Ed25519 key (Curve25519 EdDSA).
4. The resulting 64-byte signature is embedded in the record and validated on public endpoints.

---

## 2. Tamper-Evident Audit Hash Chain
Every meaningful state change produces an immutable audit block chained to the preceding block:
$$H_n = \text{SHA256}(H_{n-1} \parallel \text{EventCanonicalData})$$
- Initial block $H_0 = \text{GENESIS\_HASH}$ (64 zeros).
- Any post-facto alteration of historical submissions or decisions invalidates the downstream hash chain.
- Verified in real time via `GET /api/v1/audit/verify-chain`.

---

## 3. DPDP Act 2023 Compliance
Under the Digital Personal Data Protection Act (DPDP) 2023:
- Public verification QR endpoints strictly redact private citizen names, Aadhaar/PAN identifiers, and financial mortgage numbers.
- Public proofs provide volumetric boundaries, spatial coordinates, digital signature validity, and authority timestamps without compromising individual privacy.
