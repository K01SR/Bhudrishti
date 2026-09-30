# Bhu-Drishti 3D — Topology & QA Rule Engine

## 1. Overview
The platform enforces 12 spatial integrity rules alongside municipal FSI calculations to check that 3D volumetric parcels conform to geometric, cadastral, and infrastructural standards.

The rules are implemented in Python against Shapely geometry (`app/qa_engine/rules.py`). SFCGAL 1.5.1 is present in the PostGIS build and usable from SQL, but it does not evaluate these rules — an earlier version of this document credited the checks to it.

---

## 2. Rule Catalog (R001 to R016)

| Rule ID | Rule Name | Severity | Definition & Mathematical Check | Status in Demo |
| :--- | :--- | :--- | :--- | :--- |
| **R001** | Building Enclosure in Parent Parcel | `CRITICAL` | Building footprint polygon must intersect and be completely contained within parent land parcel boundary: $\text{ST\_Contains}(\text{Parcel}, \text{Building})$. | **PASS** |
| **R002** | Unit Enclosure in Building Envelope | `HIGH` | All vertical unit footprints must reside within the outer building envelope boundary: $\forall u \in \text{Units}: \text{ST\_Contains}(\text{Building}, u)$. | **PASS** |
| **R003** | Vertical Floor Elevation Non-Overlap | `HIGH` | Z-intervals of consecutive floor levels cannot collide: $\text{Level}_i.Z_{\max} \le \text{Level}_{i+1}.Z_{\min}$. | **PASS** |
| **R004** | Adjacent Unit Spatial Non-Overlap | `HIGH` | Adjacent units on the same floor cannot overlap in 2D or 3D: $\forall u_i, u_j: \text{Area}(\text{ST\_Intersection}(u_i, u_j)) = 0$. | **PASS** |
| **R005** | Floor Bounds Structural Consistency | `MEDIUM` | Floor slab horizontal cantilever cannot exceed approved structural setbacks. | **PASS** |
| **R006** | Positive Vertical Height Interval | `HIGH` | All volumetric units must possess positive height: $Z_{\max} > Z_{\min}$. | **PASS** |
| **R007** | Document vs Geometry Parcel Area | `MEDIUM` | Variance between deed area and calculated GIS area must be $\le 2\%$: $\frac{\lvert A_{\text{calc}} - A_{\text{doc}} \rvert}{A_{\text{doc}}} \le 0.02$. | **PASS** (0.0% variance) |
| **R008** | Multi-Source Boundary Concordance | `MEDIUM` | Alignment between GIS cadastre and processed LiDAR footprint must satisfy $\text{IoU} \ge 0.85$. | **PASS** ($\text{IoU} = 0.94$) |
| **R009** | Subsurface Clash Detection | `CRITICAL` | 3D intersection between basement foundations and underground utility lines or transit corridors: $\text{ST\_3DIntersects}(\text{Basement}, \text{Utility})$. | **FAIL (Caught!)** |
| **R010** | Duplicate Spatial Claim Detection | `CRITICAL` | Zero overlapping claims across pending builder/citizen registrations for the same spatial unit. | **PASS** |
| **R011** | Duplicate Cadastral Identity | `HIGH` | Unique 3D spatial identity across the state cadastre. | **PASS** |
| **R012** | OGC Geometric Validity & Solid Closure | `CRITICAL` | All polygons and 3D planar facets must be topologically closed without self-intersections. | **PASS** |

---

## 3. Subsurface Clash Case Study (Rule R009)
During the Hero Demonstration:
- **Building B-17 Basement Foundation:** $X \in [145.0, 175.0]$, $Y \in [144.0, 161.0]$, $Z \in [-3.5\text{m}, 0.0\text{m}]$.
- **Municipal Stormwater Main (`PIPE-DRAIN-01`):** Diameter $800\text{mm}$, runs from $[130, 150, -3.2]$ to $[190, 150, -3.2]$.
- **Finding:** The pipe physically penetrates the basement between $X=145$ and $X=175$ at depth $Z = -3.2\text{m}$.
- **System Action:** Rule R009 triggers a **CRITICAL FAIL**, flags the clash in glowing RED on the 3D viewer, and blocks automated registration until an authorized officer resolves the diversion notice.

---

## 4. Municipal FSI Auto-Check
- **Formula:** $\text{FSI} = \frac{\text{Total Built-Up Area}}{\text{Plot Area}}$
- **Airoli Sector 8 Jurisdiction Rule:** Max allowed FSI $= 2.00$
- **Building B-17 Calculation:**
  $$\text{FSI} = \frac{1,800.0\text{ m}^2}{1,000.0\text{ m}^2} = 1.800 \le 2.00 \implies \mathbf{PASS}$$
