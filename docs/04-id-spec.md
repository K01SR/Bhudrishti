# Proposed Bhu-Drishti 3D Spatial Extension Specification

> **Specification Label:** Proposed Bhu-Drishti 3D Spatial Extension — Demo Specification  
> **Disclaimer:** This identifier represents a proposed technical extension for 3D cadastral units. It does NOT supersede or replace India's official 14-character parent parcel ULPIN.

---

## 1. Identifier Template
```text
{parent_14_char_ULPIN}/{TYPE}{BUILDING}-{LEVEL}-{UNIT}-{CHECKSUM}
```

### Components:
- **`parent_14_char_ULPIN`**: The immutable official 14-character alphanumeric base parcel ID (e.g., `12345678901234`).
- **`TYPE`**: Single-character spatial domain code:
  - `S` = Surface Land Parcel
  - `B` = Building Structure
  - `L` = Floor / Level Slab
  - `U` = Vertical Volumetric Property Unit (Apartment / Office)
  - `X` = Subterranean Infrastructure (Tunnel, Utility, Pipe)
  - `E` = Elevated Structure (Skywalk, Overpass)
  - `A` = Air-Right Envelope / Column
  - `P` = Designated Parking Bay
- **`BUILDING`**: Alphanumeric structure designation (e.g., `B17`).
- **`LEVEL`**: Vertical floor code (e.g., `B1`, `G`, `L01`, `L02`, `L05`).
- **`UNIT`**: Internal unit designation (e.g., `101`, `201`, `501`, `P01`, `PIPE01`).
- **`CHECKSUM`**: Single ISO/IEC 7064 Alphanumeric Luhn Mod 36 check character.

---

## 2. Checksum Algorithm (Luhn Mod 36)
- **Alphabet:** `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ` (Radix 36).
- **Processing:** From right to left, characters are weighted alternatingly by factors $2$ and $1$.
- **Radix Summation:** If $v \times \text{factor} \ge 36$, digital sum in base 36 is applied: $\lfloor \text{prod}/36 \rfloor + (\text{prod} \pmod{36})$.
- **Check Character:** $C = (36 - (\sum \pmod{36})) \pmod{36}$.
- **Error Detection:** Detects 100% of single-character transcription errors and 100% of adjacent transposition errors.

---

## 3. National-style ULPIN Derivation

The **parent** segment of every 3D identifier is a 14-character alphanumeric parcel
identifier derived in-repo from the parcel's vertices.

> **This is not an official ULPIN and has no legal weight.** The table below
> describes what this repository *implements*. The official ULPIN specification was
> not obtained for this work, so no compliance with ECCMA, OGC, or any published
> standard is claimed or tested. No authority issues identifiers from this code.

| Attribute | Value |
|---|---|
| Issued by | No authority. Derived in-repo. |
| Length / Type | 14 characters, alphanumeric |
| Basis | Geo-referenced **lat/lon coordinates of the parcel vertices** |
| Standards tested against | None |
| Programmes | None. Not a DILRMP participant. |

`NATIONAL_ULPIN_SPEC` in `app/id_engine/national.py` is the machine-readable version of
this table and is what the UI renders.

### 3.1 Deterministic derivation (`app/id_engine/national.py`)

For offline/qualified evaluation the platform can derive a national-style parent from
real parcel geometry — the number is a pure function of the vertices, so the same
parcel always yields the same ID and any vertex edit changes it:

```text
ULPIN = {cell(2)} + {radix-36 digest of canonicalised vertices (11)} + {check(1)}
```

- `cell` — degree-band key from the parcel centroid (a local construction, not the ECCMA standard).
- digest — SHA-256 of the sorted, deduplicated, 6-decimal lat/lon vertices, folded to 11 base-36 chars.
- `check` — ISO/IEC 7064 Luhn Mod 36 check character.

Local cadastral-frame metre rings are converted to WGS84 via a documented UTM zone-43N
origin (`app/id_engine.national.local_to_latlon`) before derivation.

### 3.2 Production posture

> Official ULPIN issuance must consume the **DOLR/state ULPIN APIs** once a State has rolled
> out the identifier. The derivation above exists so vertical mapping can proceed offline; it
> never overrides a ULPIN issued by an authority, and a derived value must not be displayed
> as though it were one.

---

## 4. Vertical (3D) Extension

```text
{parent_14}/TYPE{BUILDING}-{LEVEL}-{UNIT}-{CHECKSUM}
```

Vertical slices inherit their surface parcel ULPIN unmodified and append an explicit,
checksummed **vertical layer** — enabling a single surface parcel to carry basement,
ground-through-penthouse, air-right and subterranean volumes concurrently.

### Level codes
| Code | Meaning | Z band |
|---|---|---|
| `B<n>` | Basement | below ground |
| `G` | Ground floor | `0.0–3.6` |
| `L<n>` | Upper floor | multiples of 3.6 m |
| `P` / `PH` | Penthouse / plant | top of building |

### Worked example
```text
Y1353VXHTX76VJ/UB17-L05-501-8
 └ national parent     └ vertical unit 501 on L05 of B-17, check '8'
```

- Apartment 501: `Y1353VXHTX76VJ/UB17-L05-501-8`
- Entire floor slab L03: `Y1353VXHTX76VJ/LB17-L03-ALL-H`
- Utility pipe in basement: `Y1353VXHTX76VJ/XB17-B1-PIPE01-K`

API support: `app/api/v1/ids.py` (validate), `app/id_engine/national.py` (derive + verify).
