# Bhu-Drishti 3D — 5-Minute Live Presentation Demo Script

> **North-Star Proposition:**  
> “We take fragmented spatial evidence about one property, transform it into a standardized 3D cadastral representation, automatically detect inconsistencies, route it through authority verification, preserve its history, and make the verified result interoperable and publicly verifiable.”

---

## Scene 1: State Cadastral Overview (0:00 – 0:40)
1. **Navigate to:** `State Overview` tab (`/state`).
2. **Narration:**
   > “Welcome to Bhu-Drishti 3D. We begin at the State Commissioner level for Maharashtra. Notice that unlike a generic 3D map, our dashboard tracks cadastral governance KPIs: 36 mapped parcels, 108 strata units, and critical topology discrepancies across jurisdictions.”
3. **Action:**
   > Highlight Airoli Sector 8 jurisdiction row, showing 1 critical subsurface clash and 1 suspected unauthorized change. Click **Open Twin** to enter the Property Workspace.

---

## Scene 2: The Hero Property — Building B-17 (0:40 – 1:20)
1. **Screen:** `Property Workspace` (`/`).
2. **Narration:**
   > “Here is our hero parcel CTS-100 (Official 14-char ULPIN `12345678901234`). On this parcel sits Building B-17. The parent ULPIN remains untouched. The child vertical units receive our Proposed 3D Extension ID with an ISO 7064 Luhn Mod 36 checksum.”
3. **Action:**
   > Open the **Evidence Panel** on the bottom right. Show the 6 ingested evidence streams (GIS parcel, Drone E1/E2, airborne LiDAR, architectural floor plans, CORS GNSS, DEM). Point out the measured point density (32.4 pts/m²).

---

## Scene 3: Automated AI Extraction & Processing (1:20 – 2:00)
1. **Action:** Click **Process Property** in the top header.
2. **Narration:**
   > “When the builder submits spatial data, the system runs our automated processing pipeline: statistical ground separation, RANSAC hull polygonization, and Z-density peak histogram segmentation. In less than 1.5 seconds, the system extracts the building footprint with 94% IoU and segments 5 above-ground floors and 1 subterranean basement.”

---

## Scene 4: Underground X-Ray & Subsurface Clash (2:00 – 2:45)
1. **Action:** Click **Underground X-Ray** button on the 3D viewer.
2. **Visual Transformation:**
   > Ground fades to 20% opacity. Building B-17 becomes translucent. The subterranean basement (-3.5m to 0m), municipal stormwater main `PIPE-DRAIN-01`, and deep Metro Line 2A tunnel become visible.
3. **Clash Alert:**
   > Point out the red glowing sphere at Z = -3.2m where the stormwater pipe intersects the basement foundation perimeter.
4. **Narration:**
   > “Our PostGIS topology engine executes 12 strict geometric rules. Notice rule R009: Subterranean Infrastructure Clash. The system caught a critical physical collision before construction approval, protecting public assets.”

---

## Scene 5: Explode, Slice & Rights Visualizer (2:45 – 3:30)
1. **Action 1:** Move the **Explode Floors** slider to 80%.
   > Observe each floor slab and its vertical apartment units separating vertically along the Z-axis.
2. **Action 2:** Switch **3D Color Mode** to `Rights & Mortgages`.
   > Point out Unit 201 turning RED.
3. **Narration:**
   > “Selecting Unit 201 reveals its encumbrance ledger: registered ownership to Karan & Priya Malhotra, but an active ₹85,00,000 mortgage lien to State Bank of India and a fire egress access easement. 3D cadastre allows banks and buyers to visually verify volumetric encumbrances.”

---

## Scene 6: Temporal Monitoring — Detected Change Between Two Generated Epochs (3:30 – 4:10)
1. **Action:** Switch to the **Time Slider** tab in the lower panel. Toggle from `2026 Epoch 1 (Baseline)` to `2027 Epoch 2 (Monitoring)`.
2. **Visual Transformation:**
   > A 6th floor appears on top of Building B-17 (+3.5m height, 4 new units).
3. **Narration:**
   > “Switching the time slider compares two epochs and our differencing shows a +3.5 m height increase with an added 6th floor. Both epochs are generated for this demo, so this is a change between two datasets and not a detection of anything real. We label it 'Detected change (unverified)' and hand it to a human reviewer; nothing here decides what is permitted.”

---

## Scene 7: Natural Language 'Ask-The-Map' & Public QR Proof (4:10 – 5:00)
1. **Action 1:** Click **Ask the Map** in the navbar. Click suggestion: *Show underground clashes*.
   > Watch the 3D camera auto-focus and highlight the clash point in red.
2. **Action 2:** Click **Verify QR Proof** in the header.
   > The QR code and Ed25519 signature modal appear. Click **Download Certificate** or scan the QR code.
3. **Narration:**
   > “Once approved by the district verifier, the record is signed using Ed25519 and anchored into our tamper-evident SHA-256 audit hash chain. Any citizen can scan the public QR code to verify approved boundaries and digital signatures without exposing private owner data—fully compliant with the DPDP Act 2023.”
4. **Closing Sentence:**
   > “That is Bhu-Drishti 3D: Evidence $\rightarrow$ Intelligence $\rightarrow$ Verification $\rightarrow$ Tamper-Evident 3D Cadastre.”
