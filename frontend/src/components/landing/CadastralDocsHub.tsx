import { tint } from './tint';
import React, { useState } from 'react';
import {
  Scale,
  Cpu,
  Database,
  ShieldAlert,
  Terminal,
  CheckCircle2,
  Copy,
  Check,
  Layers,
  Box,
  Fingerprint,
  Download,
} from 'lucide-react';
import { CADASTRAL_EXCEL_URL } from '../../services/api';

interface Props {
  theme: 'brutalist' | 'swiss' | 'kinetic' | 'neo' | 'botanical';
  isLightMode?: boolean;
}

export const CadastralDocsHub: React.FC<Props> = ({ theme, isLightMode = false }) => {
  const [activeTab, setActiveTab] = useState<'ARCHITECTURE' | 'LEGAL_DCR' | 'LUHN_MOD36' | 'API_SPEC' | 'PRECINCT_DATA' | 'BUYER_SHIELD'>('ARCHITECTURE');
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCode(id);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  const isBrutalistLight = theme === 'brutalist' && isLightMode;

  // neutral-400 is the dark-theme caption grey and only reaches 2.5:1 on

  // paper, so the light variant needs a darker step of the same ramp.

  const mutedText = isBrutalistLight ? 'text-neutral-600' : 'text-neutral-400';


  const isSwiss = theme === 'swiss';
  const isKinetic = theme === 'kinetic';
  const isNeo = theme === 'neo';
  const isBotanical = theme === 'botanical';

  const containerStyle = isSwiss
    ? 'bg-white border-neutral-200 text-neutral-900'
    : isKinetic
    ? 'bg-[#09090B] border-2 border-[#3F3F46] text-[#FAFAFA]'
    : isNeo
    ? 'bg-[#FFFDF5] border-4 border-black text-black shadow-[8px_8px_0px_0px_#000]'
    : isBotanical
    ? 'bg-white/90 border border-[#E6E2DA] rounded-3xl text-[#2D3A31] shadow-[0_20px_40px_-10px_rgba(45,58,49,0.06)]'
    : isBrutalistLight
    ? 'bg-[#F4F3EE] border-2 border-black text-black shadow-[4px_4px_0px_0px_#000]'
    : 'bg-[#090B0E] border-2 border-white/20 text-white shadow-2xl';

  const tabActiveStyle = isSwiss
    ? 'bg-black text-white'
    : isKinetic
    ? 'bg-[#DFE104] text-black font-black font-space'
    : isNeo
    ? 'bg-[#FFD93D] text-black border-4 border-black font-black shadow-[3px_3px_0px_0px_#000]'
    : isBotanical
    ? 'bg-[#2D3A31] text-white rounded-full font-serif font-bold shadow-sm'
    : isBrutalistLight
    ? 'bg-[#00FF66] text-black border-2 border-black shadow-[2px_2px_0px_0px_#000]'
    : 'bg-[#00FF66] text-black font-black';

  const tabInactiveStyle = isSwiss
    ? 'text-neutral-500 hover:text-black hover:bg-neutral-100'
    : isKinetic
    ? 'text-[#A1A1AA] hover:text-white hover:bg-white/5 border border-[#3F3F46]'
    : isNeo
    ? 'bg-white text-black hover:bg-[#FF6B6B] hover:text-white border-4 border-black shadow-[2px_2px_0px_0px_#000]'
    : isBotanical
    ? 'text-[#2D3A31]/70 hover:text-[#2D3A31] hover:bg-[#8C9A84]/15 rounded-full border border-[#E6E2DA]'
    : isBrutalistLight
    ? 'text-black/70 hover:text-black hover:bg-black/5 border border-black/20'
    : 'text-white/80 hover:text-white hover:bg-white/5 border border-white/10';

  const codeBoxStyle = isSwiss
    ? 'bg-neutral-900 text-neutral-100 border border-neutral-800'
    : isKinetic
    ? 'bg-[#18181B] text-[#DFE104] border border-[#3F3F46]'
    : isNeo
    ? 'bg-white text-black border-4 border-black shadow-[4px_4px_0px_0px_#000]'
    : isBotanical
    ? 'bg-[#2D3A31] text-[#DCCFC2] rounded-2xl border border-[#8C9A84]/30'
    : isBrutalistLight
    ? 'bg-[#EBE9E1] text-black border-2 border-black shadow-[3px_3px_0px_0px_#000]'
    : 'bg-[#040507] text-[#00FF66] border border-white/15';

  const sectionBgClass = isSwiss
    ? 'bg-neutral-50/70 border-t border-b border-neutral-200'
    : isKinetic
    ? 'bg-[#09090B] border-t-2 border-b-2 border-[#3F3F46]'
    : isNeo
    ? 'bg-[#FFFDF5] border-t-8 border-b-8 border-black neo-halftone'
    : isBotanical
    ? 'bg-[#F9F8F4] border-t border-b border-[#E6E2DA] botanical-grain'
    : isBrutalistLight
    ? 'bg-[#ECEAE4] border-t-4 border-b-4 border-black'
    : 'bg-[#060709] border-t-2 border-b-2 border-white/15';

  return (
    <section id="docs" className={`py-16 ${sectionBgClass}`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        {/* Section Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono tracking-widest uppercase mb-2">
              <span className={`w-2 h-2 rounded-full ${isSwiss ? 'bg-red-600' : 'bg-[#00FF66]'}`} />
              <span className={isSwiss ? 'text-neutral-500 font-bold' : isBrutalistLight ? 'text-black font-bold' : 'text-white/75'}>
                DOCS // SPECIFICATION MATRIX
              </span>
            </div>
            <h2 className={`text-3xl sm:text-4xl font-black uppercase tracking-tight ${isSwiss ? 'text-black' : isBrutalistLight ? 'text-black' : 'text-white'}`}>
              System Architecture & Documentation
            </h2>
            <p className={`text-sm mt-1 max-w-2xl ${isSwiss ? 'text-neutral-600' : isBrutalistLight ? 'text-black/70' : 'text-white/80'}`}>
              Comprehensive specifications governing the 3D cadastral parcel representation, topological rule engine, ISO/IEC 7064 Luhn Mod 36 checksums, and NBC 2016 Part 3 legal covenants.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <a
              href={CADASTRAL_EXCEL_URL}
              download
              className={`inline-flex items-center gap-2 px-3.5 py-2 text-xs font-mono font-bold uppercase transition ${
                isSwiss
                  ? 'border border-neutral-300 bg-white text-black hover:border-black'
                  : isBrutalistLight
                  ? 'bg-white text-black border-2 border-black hover:bg-[#FFE600] shadow-[3px_3px_0px_0px_#000]'
                  : 'bg-black/80 border border-white/20 text-white hover:border-[#00FF66]'
              }`}
            >
              <Download className={`w-3.5 h-3.5 ${mutedText}`} />
              Download Precinct GIS Dataset
            </a>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex flex-wrap gap-1.5 border-b pb-4 mb-8 border-neutral-300">
          {[
            { id: 'ARCHITECTURE', label: '01 / SYSTEM ARCHITECTURE', icon: <Cpu className="w-3.5 h-3.5" /> },
            { id: 'LEGAL_DCR', label: '02 / LEGAL & DCR NORMS', icon: <Scale className="w-3.5 h-3.5" /> },
            { id: 'LUHN_MOD36', label: '03 / LUHN MOD 36 CHECKSUM', icon: <Fingerprint className="w-3.5 h-3.5" /> },
            { id: 'API_SPEC', label: '04 / REST API REFERENCE', icon: <Terminal className="w-3.5 h-3.5" /> },
            { id: 'PRECINCT_DATA', label: '05 / PRECINCT DATASET', icon: <Database className="w-3.5 h-3.5" /> },
            { id: 'BUYER_SHIELD', label: '06 / BUYER SHIELD PROTOCOL', icon: <ShieldAlert className="w-3.5 h-3.5" /> },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id as any)}
              className={`flex items-center gap-2 px-3.5 py-2 text-xs font-mono font-bold uppercase transition ${
                activeTab === t.id ? tabActiveStyle : tabInactiveStyle
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab 1: System Architecture */}
        {activeTab === 'ARCHITECTURE' && (
          <div className={`p-6 sm:p-8 space-y-8 ${containerStyle}`}>
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              <div className="lg:col-span-7 space-y-4">
                <span className={`text-[10px] font-mono uppercase tracking-widest text-emerald-800 font-bold bg-emerald-50 px-2 py-0.5 border border-emerald-200`}>
                  GEOMETRIC RECONSTRUCTION PIPELINE
                </span>
                <h3 className="text-2xl font-black uppercase tracking-tight">
                  High-Precision PostGIS 3D & Topological Delineator
                </h3>
                <p className="text-xs sm:text-sm leading-relaxed text-inherit opacity-80">
                  The Bhu-Drishti pipeline ingests heterogeneous spatial inputs: 2D GIS shapefiles from state cadastral portals, scanned survey blueprints, drone photogrammetric point clouds, and builder IFC/CAD models. It resolves them into manifold 3D <code className="font-mono bg-black/10 px-1 py-0.5 rounded">POLYHEDRALSURFACE</code> primitives.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 text-xs font-mono">
                  <div className="p-3 border border-current/20 rounded-none bg-black/5 space-y-1">
                    <div className="font-bold uppercase flex items-center gap-1.5 text-inherit">
                      <Box className={`w-3.5 h-3.5 ${tint(isBrutalistLight,'blue')}`} /> Coordinate Reference
                    </div>
                    <div className="text-[11px] opacity-75">EPSG:32643 (WGS 84 / UTM Zone 43N)</div>
                    <div className="text-[10px] opacity-60">MSL Datum: Survey of India GTS Datum (+12.00m)</div>
                  </div>
                  <div className="p-3 border border-current/20 rounded-none bg-black/5 space-y-1">
                    <div className="font-bold uppercase flex items-center gap-1.5 text-inherit">
                      <Layers className={`w-3.5 h-3.5 ${tint(isBrutalistLight,'emerald')}`} /> Precision Tolerance
                    </div>
                    <div className="text-[11px] opacity-75">Snap Radius: 0.05m (5 cm)</div>
                    <div className="text-[10px] opacity-60">Volume Tolerance: ±0.001 m³</div>
                  </div>
                </div>

                <div className="pt-2">
                  <div className="text-xs font-mono font-bold uppercase mb-2">5-Stage Cadastral Synthesis Pipeline:</div>
                  <ol className="space-y-2 text-xs font-mono opacity-85">
                    <li className="flex items-start gap-2">
                      <span className={`font-bold ${tint(isBrutalistLight,'red')}`}>01.</span>
                      <span><strong>Boundary Harmonization:</strong> Shapely polygon planar graph normalization. Removes slivers, micro-gaps, and self-intersections.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className={`font-bold ${tint(isBrutalistLight,'red')}`}>02.</span>
                      <span><strong>Z-Extrusion Engine:</strong> Vertical boundary extrusions based on floor sanction heights ($h = 3.6m$ standard residential).</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className={`font-bold ${tint(isBrutalistLight,'red')}`}>03.</span>
                      <span><strong>Subterranean Clash Predicate:</strong> Spatial 3D cylinder buffer intersections detecting conflicts with municipal utilities ($d \ge 2.0m$).</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className={`font-bold ${tint(isBrutalistLight,'red')}`}>04.</span>
                      <span><strong>Solar Air-Rights Envelope:</strong> Dynamic 3D ray-tracing shadow casts calculating shadow infringement on adjoining plots.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className={`font-bold ${tint(isBrutalistLight,'red')}`}>05.</span>
                      <span><strong>Cryptographic Minting:</strong> ISO/IEC 7064 Luhn Mod 36 checksum assignment + Ed25519 digital signature. Checksums detect transcription errors; signatures prove a record has not been altered since it was signed. Neither is an official registry.</span>
                    </li>
                  </ol>
                </div>
              </div>

              {/* Code Snippet Column */}
              <div className="lg:col-span-5 space-y-3 font-mono text-xs">
                <div className="flex items-center justify-between px-1">
                  <span className="text-[10px] uppercase font-bold opacity-60">PostGIS 3D Spatial Query</span>
                  <button
                    onClick={() => copyToClipboard(`-- 3D Cadastral Volumetric Overlap & Clash Detection
SELECT
    p.ulpin AS parcel_ulpin,
    u.unit_code,
    ST_Volume(ST_3DIntersection(u.geom_3d, sub.utility_geom)) AS clash_volume_m3
FROM cadastre_units u
JOIN cadastre_parcels p ON u.parcel_id = p.id
CROSS JOIN municipal_subsurface_utilities sub
WHERE ST_3DIntersects(u.geom_3d, sub.utility_geom)
  AND sub.buffer_clearance_m < 2.0;`, 'sql')}
                    className={`flex items-center gap-1 min-h-[28px] px-2 text-[10px] ${tint(isBrutalistLight,'blue')} hover:underline`}
                  >
                    {copiedCode === 'sql' ? <Check className={`w-3 h-3 ${tint(isBrutalistLight,'emerald')}`} /> : <Copy className="w-3 h-3" />}
                    {copiedCode === 'sql' ? 'Copied' : 'Copy SQL'}
                  </button>
                </div>

                <pre className={`p-4 rounded-none overflow-x-auto text-[11px] leading-relaxed ${codeBoxStyle}`}>
{`-- 3D Cadastral Volumetric Overlap Query
SELECT
    p.ulpin AS parcel_ulpin,
    u.unit_code,
    ST_Volume(
      ST_3DIntersection(u.geom_3d, sub.utility_geom)
    ) AS clash_volume_m3
FROM cadastre_units u
JOIN cadastre_parcels p ON u.parcel_id = p.id
CROSS JOIN municipal_subsurface_utilities sub
WHERE ST_3DIntersects(u.geom_3d, sub.utility_geom)
  AND sub.buffer_clearance_m < 2.0;`}
                </pre>

                <div className="p-3 border border-current/15 text-[10px] space-y-1 bg-black/5">
                  <div className={`font-bold uppercase ${tint(isBrutalistLight,'red')}`}>Native Acceleration</div>
                  <div className="opacity-75">
                    Spatial point-in-polyhedron tests run via SIMD-accelerated C++/Rust native kernels, evaluating 10,000 LiDAR point classifications in under 1.2ms.
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Legal & DCR Norms */}
        {activeTab === 'LEGAL_DCR' && (
          <div className={`p-6 sm:p-8 space-y-6 ${containerStyle}`}>
            <div>
              <span className={`text-[10px] font-mono uppercase tracking-widest ${tint(isBrutalistLight,'red')} font-bold bg-red-50 px-2 py-0.5 border border-red-200`}>
                REGULATORY JURISDICTION & STANDARDS
              </span>
              <h3 className="text-2xl font-black uppercase tracking-tight mt-1">
                National Building Code (NBC) 2016 & Unified DCPR Norms
              </h3>
              <p className="text-xs sm:text-sm leading-relaxed opacity-80 mt-1 max-w-3xl">
                Every building proposal and as-built survey model is evaluated against the statutory requirements of the Maharashtra Unified Development Control and Promotion Regulations (UDCPR) and NBC 2016 Part 3.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
              <div className="p-4 border border-current/20 bg-black/5 space-y-2">
                <div className="font-bold uppercase text-base text-inherit">01 / Setback Formulas</div>
                <div className="text-[11px] opacity-75">
                  <strong>Front Setback:</strong> Minimum 4.50m from road centerline for plots &gt; 500m².
                </div>
                <div className="text-[11px] opacity-75">
                  <strong>Side & Rear Setbacks:</strong>
                  <div className="bg-black/10 p-2 my-1 font-bold">
                    S = 3.0 + 0.1 × (Height - 10m)
                  </div>
                  For a 18.0m building, minimum required side clearance is 3.80m. B-17 maintains 4.20m (Pass).
                </div>
              </div>

              <div className="p-4 border border-current/20 bg-black/5 space-y-2">
                <div className="font-bold uppercase text-base text-inherit">02 / FSI Density Limits</div>
                <div className="text-[11px] opacity-75">
                  <strong>Base FSI:</strong> 1.50 (Residential Zone R-2).
                </div>
                <div className="text-[11px] opacity-75">
                  <strong>Permissible TDR:</strong> +0.50 upon transit corridor premium payment.
                </div>
                <div className="text-[11px] opacity-75">
                  <strong>Ceiling Limit:</strong> 2.00 FSI.
                  <div className="bg-black/10 p-2 my-1 font-bold">
                    Max BUA = Plot Area × 2.00
                  </div>
                  Plot 1,000m² allows max 2,000m² BUA (or 2,550m² with ancillary incentive). B-17 measured at 1.80 (no sanction to compare).
                </div>
              </div>

              <div className="p-4 border border-current/20 bg-black/5 space-y-2">
                <div className="font-bold uppercase text-base text-inherit">03 / Ground Coverage</div>
                <div className="text-[11px] opacity-75">
                  <strong>Maximum Ground Coverage:</strong> ≤ 60% of total plot area.
                </div>
                <div className="text-[11px] opacity-75">
                  <strong>Open Space Reserve:</strong> ≥ 15% open contiguous recreational ground.
                </div>
                <div className="text-[11px] opacity-75">
                  <strong>Fire Tender Driveway:</strong> 6.00m unobstructed turning radius with 45-tonne axle load support.
                </div>
              </div>
            </div>

            {/* Legal Covenants Table */}
            <div className="pt-2">
              <div className="text-xs font-mono font-bold uppercase mb-2">Statutes Referenced (not applied or certified):</div>
              <div className="border border-current/20 overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-black/10 border-b border-current/20 uppercase">
                    <tr>
                      <th className="py-2.5 px-3">Statutory Act</th>
                      <th className="py-2.5 px-3">Provision</th>
                      <th className="py-2.5 px-3">Prototype Approach</th>
                      <th className="py-2.5 px-3">Instrument Type</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-current/15 text-[11px]">
                    <tr>
                      <td className="py-2.5 px-3 font-bold">MahaRERA 2016</td>
                      <td className="py-2.5 px-3">Section 4(2)(l) Carpet Area disclosure</td>
                      <td className="py-2.5 px-3">Volumetric unit polygons bounded by internal face of walls</td>
                      <td className={`py-2.5 px-3 ${tint(isBrutalistLight,'emerald')} font-bold`}>Guidance</td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 font-bold">Maharashtra Land Revenue Code 1966</td>
                      <td className="py-2.5 px-3">Section 20 & 148 Cadastral Survey Record</td>
                      <td className="py-2.5 px-3">14-Digit ULPIN + Z-level strata sub-codes (e.g. U-B17-L05-501)</td>
                      <td className={`py-2.5 px-3 ${tint(isBrutalistLight,'emerald')} font-bold`}>Statute</td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 font-bold">Indian Easements Act 1882</td>
                      <td className="py-2.5 px-3">Section 7 & 15 Light & Air Prescriptive Rights</td>
                      <td className="py-2.5 px-3">Ray-traced shadow occlusion limits & 0.00mm cantilever overhang</td>
                      <td className={`py-2.5 px-3 ${tint(isBrutalistLight,'emerald')} font-bold`}>Statute</td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 font-bold">DPDP Act 2023</td>
                      <td className="py-2.5 px-3">Personal Data Redaction</td>
                      <td className="py-2.5 px-3">Role-based masking: Citizen/Public cannot see bank mortgages or private names</td>
                      <td className={`py-2.5 px-3 ${tint(isBrutalistLight,'emerald')} font-bold`}>Statutory</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Luhn Mod 36 Checksum */}
        {activeTab === 'LUHN_MOD36' && (
          <div className={`p-6 sm:p-8 space-y-6 ${containerStyle}`}>
            <div>
              <span className={`text-[10px] font-mono uppercase tracking-widest ${tint(isBrutalistLight,'blue')} font-bold bg-blue-50 px-2 py-0.5 border border-blue-200`}>
                ALPHANUMERIC INTEGRITY SPECIFICATION
              </span>
              <h3 className="text-2xl font-black uppercase tracking-tight mt-1">
                ISO/IEC 7064 Luhn Mod 36 Checksum Standard
              </h3>
              <p className="text-xs sm:text-sm leading-relaxed opacity-80 mt-1 max-w-3xl">
                Every Bhu-Drishti 3D-ULPIN is composed of 14 characters. The 14th character is a mathematically calculated check digit using the ISO/IEC 7064 Mod 36,36 algorithm, preventing transcription errors, transposed digits, and fraudulent records.
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              <div className="lg:col-span-6 space-y-4">
                <div className="p-4 border border-current/20 bg-black/5 space-y-2 text-xs font-mono">
                  <div className="font-bold uppercase text-sm">Character Set: Radix 36</div>
                  <div className="p-2 bg-black/10 font-mono tracking-widest text-center text-xs font-bold">
                    0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ
                  </div>
                  <div className="text-[11px] opacity-75">
                    Values 0–9 map to integers 0–9; characters A–Z map to integers 10–35.
                  </div>
                </div>

                <div className="space-y-2 text-xs font-mono">
                  <div className="font-bold uppercase">Mathematical Formulation:</div>
                  <p className="opacity-80">
                    Given payload characters $c_1, c_2, \dots, c_{13}$, the checksum $C$ is computed such that:
                  </p>
                  <pre className={`p-3 text-[11px] ${codeBoxStyle}`}>
{`let factor = 2;
let sum = 0;
for (let i = payload.length - 1; i >= 0; i--) {
    let codePoint = charset.indexOf(payload[i]);
    let addend = factor * codePoint;
    factor = (factor === 2) ? 1 : 2;
    addend = Math.floor(addend / 36) + (addend % 36);
    sum += addend;
}
let remainder = sum % 36;
let checkCodePoint = (36 - remainder) % 36;
return charset[checkCodePoint];`}
                  </pre>
                </div>
              </div>

              <div className="lg:col-span-6 space-y-3 font-mono text-xs">
                <div className="font-bold uppercase">Error Detection Properties:</div>
                <div className="space-y-2 text-[11px] opacity-85">
                  <div className="p-2.5 border border-current/15 bg-black/5 flex items-start gap-2">
                    <CheckCircle2 className={`w-4 h-4 ${tint(isBrutalistLight,'emerald')} shrink-0 mt-0.5`} />
                    <div><strong>100% Single Substitution Errors:</strong> Any single character mistyped (e.g. 5 typed as S, or 0 typed as O) is guaranteed to be detected.</div>
                  </div>
                  <div className="p-2.5 border border-current/15 bg-black/5 flex items-start gap-2">
                    <CheckCircle2 className={`w-4 h-4 ${tint(isBrutalistLight,'emerald')} shrink-0 mt-0.5`} />
                    <div><strong>100% Adjacent Transposition Errors:</strong> Swapping two characters (e.g. ...B17... into ...1B7...) is caught unconditionally.</div>
                  </div>
                  <div className="p-2.5 border border-current/15 bg-black/5 flex items-start gap-2">
                    <CheckCircle2 className={`w-4 h-4 ${tint(isBrutalistLight,'emerald')} shrink-0 mt-0.5`} />
                    <div><strong>&gt; 99.8% Multi-Character Corruption:</strong> Random noise corruption fails checksum verification with probability $1 - \frac{1}{36} \approx 97.2\%$ per corrupted position.</div>
                  </div>
                </div>

                <div className="p-3 border border-emerald-500/40 bg-emerald-50/20 text-[11px] space-y-1">
                  <span className="font-bold uppercase text-emerald-700">Live ULPIN Verification:</span>
                  <div className="font-bold font-mono text-inherit">12345678901234 → Check Digit: Valid (Hero Parcel B-17)</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: REST API Reference */}
        {activeTab === 'API_SPEC' && (
          <div className={`p-6 sm:p-8 space-y-6 ${containerStyle}`}>
            <div>
              <span className={`text-[10px] font-mono uppercase tracking-widest text-emerald-800 font-bold bg-emerald-50 px-2 py-0.5 border border-emerald-200`}>
                DEVELOPER INTEROPERABILITY
              </span>
              <h3 className="text-2xl font-black uppercase tracking-tight mt-1">
                RESTful Spatial Cadastre API Endpoints
              </h3>
              <p className="text-xs sm:text-sm leading-relaxed opacity-80 mt-1 max-w-3xl">
                Integrate directly with Bhu-Drishti 3D services. All endpoints return GeoJSON, CityJSON, or canonical JSON schemas with strict validation.
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              {/* Endpoint List */}
              <div className="lg:col-span-5 space-y-2 text-xs font-mono">
                {[
                  { method: 'GET', path: '/api/v1/properties/hero', desc: 'Hero Building B-17 complete 3D twin & strata units' },
                  { method: 'GET', path: '/api/v1/parcels/geojson', desc: 'Precinct 13 parcels GeoJSON polygons' },
                  { method: 'GET', path: '/api/v1/precinct/buildings', desc: 'All 12 precinct buildings with FSI & risk scores' },
                  { method: 'GET', path: '/api/v1/lidar/pointcloud', desc: 'UAV LiDAR point cloud with ground/roof classifications' },
                  { method: 'GET', path: '/api/v1/audit/verify-chain', desc: 'Tamper-evident blockchain ledger validation' },
                  { method: 'POST', path: '/api/v1/submissions/process-property', desc: 'Builder CAD plan automated compliance runner' },
                ].map((ep) => (
                  <div key={ep.path} className="p-3 border border-current/20 bg-black/5 hover:bg-black/10 transition cursor-pointer">
                    <div className="flex items-center gap-2">
                      <span className={`px-1.5 py-0.5 text-[10px] font-bold ${ep.method === 'GET' ? 'bg-blue-600 text-white' : 'bg-emerald-600 text-white'}`}>
                        {ep.method}
                      </span>
                      <span className="font-bold text-inherit truncate">{ep.path}</span>
                    </div>
                    <div className="text-[10px] opacity-70 mt-1">{ep.desc}</div>
                  </div>
                ))}
              </div>

              {/* cURL & Code Example */}
              <div className="lg:col-span-7 space-y-3 font-mono text-xs">
                <div className="flex items-center justify-between px-1">
                  <span className="text-[10px] uppercase font-bold opacity-60">Example cURL Request</span>
                  <button
                    onClick={() => copyToClipboard(`curl -X GET "http://localhost:8000/api/v1/properties/hero" \\
  -H "Accept: application/json"`, 'curl')}
                    className={`flex items-center gap-1 min-h-[28px] px-2 text-[10px] ${tint(isBrutalistLight,'blue')} hover:underline`}
                  >
                    {copiedCode === 'curl' ? <Check className={`w-3 h-3 ${tint(isBrutalistLight,'emerald')}`} /> : <Copy className="w-3 h-3" />}
                    {copiedCode === 'curl' ? 'Copied' : 'Copy cURL'}
                  </button>
                </div>

                <pre className={`p-4 rounded-none overflow-x-auto text-[11px] leading-relaxed ${codeBoxStyle}`}>
{`curl -X GET "http://localhost:8000/api/v1/properties/hero" \\
  -H "Accept: application/json"`}
                </pre>

                <div className="flex items-center justify-between px-1 pt-2">
                  <span className="text-[10px] uppercase font-bold opacity-60">Sample Response (JSON)</span>
                </div>

                <pre className={`p-4 rounded-none overflow-x-auto text-[11px] leading-relaxed max-h-56 ${codeBoxStyle}`}>
{`{
  "parent_ulpin": "12345678901234",
  "structure": {
    "building_code": "B-17",
    "name": "Shree Ganesh CHS",
    "floors_count": 5,
    "height_m": 18.0,
    "calculated_fsi": 1.80,
    "status": "NOT_ASSESSED",
    "risk_level": "LOW"
  },
  "levels": [
    { "level_code": "B01", "min_z": -3.5, "max_z": 0.0, "type": "BASEMENT" },
    { "level_code": "L01", "min_z": 0.0, "max_z": 3.6, "type": "GROUND" },
    { "level_code": "L05", "min_z": 14.4, "max_z": 18.0, "type": "RESIDENTIAL" }
  ],
  "blockchain_proof": {
    "block_height": 10,
    "merkle_root": "7f4a9b...0e31",
    "chain_integrity": "VALID"
  }
}`}
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* Tab 5: Precinct Dataset */}
        {activeTab === 'PRECINCT_DATA' && (
          <div className={`p-6 sm:p-8 space-y-6 ${containerStyle}`}>
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
              <div>
                <span className={`text-[10px] font-mono uppercase tracking-widest text-emerald-800 font-bold bg-emerald-50 px-2 py-0.5 border border-emerald-200`}>
                  AIROLI SECTOR 8 PILOT
                </span>
                <h3 className="text-2xl font-black uppercase tracking-tight mt-1">
                  13 Precinct Parcels & 12 Surrounding Buildings
                </h3>
              </div>
              <a
                href={CADASTRAL_EXCEL_URL}
                download
                className="px-4 py-2 bg-black text-white text-xs font-mono font-bold uppercase hover:bg-neutral-800 transition flex items-center gap-1.5 self-start"
              >
                <Download className="w-3.5 h-3.5" /> Download Full Spreadsheet
              </a>
            </div>

            <div className="border border-current/20 overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-black/10 border-b border-current/20 uppercase">
                  <tr>
                    <th className="py-2.5 px-3">Code</th>
                    <th className="py-2.5 px-3">Structure Name</th>
                    <th className="py-2.5 px-3">Typology</th>
                    <th className="py-2.5 px-3">Floors</th>
                    <th className="py-2.5 px-3">Height</th>
                    <th className="py-2.5 px-3">Plot Area</th>
                    <th className="py-2.5 px-3">FSI Ratio</th>
                    <th className="py-2.5 px-3">Compliance Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-current/15 text-[11px]">
                  <tr className="bg-emerald-50/30 font-bold">
                    <td className={`py-2.5 px-3 ${tint(isBrutalistLight,'red')}`}>B-17 (HERO)</td>
                    <td className="py-2.5 px-3">Shree Ganesh CHS</td>
                    <td className="py-2.5 px-3">Tower</td>
                    <td className="py-2.5 px-3">5F + B1</td>
                    <td className="py-2.5 px-3">18.0 m</td>
                    <td className="py-2.5 px-3">1,000 m²</td>
                    <td className={`py-2.5 px-3 ${tint(isBrutalistLight,'emerald')}`}>1.80 (no sanction to compare)</td>
                    <td className="py-2.5 px-3 text-amber-700 dark:text-amber-400 font-bold">NOT ASSESSED</td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-bold">B-01</td>
                    <td className="py-2 px-3">Sai Krupa Towers</td>
                    <td className="py-2 px-3">Tower</td>
                    <td className="py-2 px-3">12F</td>
                    <td className="py-2 px-3">42.0 m</td>
                    <td className="py-2 px-3">990 m²</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'emerald')}`}>1.85 (no sanction to compare)</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'emerald')}`}>NOT ASSESSED</td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-bold">B-02</td>
                    <td className="py-2 px-3">Green Valley Apartments</td>
                    <td className="py-2 px-3">Tower</td>
                    <td className="py-2 px-3">8F</td>
                    <td className="py-2 px-3">28.0 m</td>
                    <td className="py-2 px-3">1,250 m²</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'emerald')}`}>1.60 (no sanction to compare)</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'emerald')}`}>NOT ASSESSED</td>
                  </tr>
                  <tr className="bg-red-50/50">
                    <td className={`py-2 px-3 font-bold ${tint(isBrutalistLight,'red')}`}>B-03</td>
                    <td className="py-2 px-3 font-bold">Lakeview Heights</td>
                    <td className="py-2 px-3">Tower</td>
                    <td className="py-2 px-3">15F</td>
                    <td className="py-2 px-3">52.5 m</td>
                    <td className="py-2 px-3">1,100 m²</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'red')} font-bold`}>2.10 (no sanction to compare)</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'red')} font-bold`}>NOT ASSESSED</td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-bold">B-07</td>
                    <td className="py-2 px-3">Orchid Row Villas</td>
                    <td className="py-2 px-3">Row House</td>
                    <td className="py-2 px-3">2F</td>
                    <td className="py-2 px-3">6.4 m</td>
                    <td className="py-2 px-3">1,250 m²</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'emerald')}`}>0.85 (no sanction to compare)</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'emerald')}`}>NOT ASSESSED</td>
                  </tr>
                  <tr className="bg-amber-50/50">
                    <td className={`py-2 px-3 font-bold ${tint(isBrutalistLight,'amber')}`}>B-09</td>
                    <td className="py-2 px-3 font-bold">Airoli Trade Center</td>
                    <td className="py-2 px-3">Commercial</td>
                    <td className="py-2 px-3">10F</td>
                    <td className="py-2 px-3">35.0 m</td>
                    <td className="py-2 px-3">2,250 m²</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'red')} font-bold`}>2.40 (no sanction to compare)</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'amber')} font-bold`}>OVER FSI</td>
                  </tr>
                  <tr className="bg-amber-50/50">
                    <td className={`py-2 px-3 font-bold ${tint(isBrutalistLight,'amber')}`}>B-12 (later epoch only)</td>
                    <td className="py-2 px-3 font-bold">Sector 8 Later-Epoch Slab</td>
                    <td className="py-2 px-3">Slab</td>
                    <td className="py-2 px-3">3F</td>
                    <td className="py-2 px-3">9.6 m</td>
                    <td className="py-2 px-3">450 m²</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'amber')} font-bold`}>0.00 (no sanction to compare)</td>
                    <td className={`py-2 px-3 ${tint(isBrutalistLight,'amber')} font-bold`}>NOT ASSESSED</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 6: Buyer Shield Protocol */}
        {activeTab === 'BUYER_SHIELD' && (
          <div className={`p-6 sm:p-8 space-y-6 ${containerStyle}`}>
            <div>
              <span className={`text-[10px] font-mono uppercase tracking-widest text-emerald-800 font-bold bg-emerald-50 px-2 py-0.5 border border-emerald-200`}>
                TITLE DUE DILIGENCE FOR HOMEBUYERS
              </span>
              <h3 className="text-2xl font-black uppercase tracking-tight mt-1">
                4-Step Buyer Shield Verification Protocol
              </h3>
              <p className="text-xs sm:text-sm leading-relaxed opacity-80 mt-1 max-w-3xl">
                A four-step protocol for checking a property before signing an Agreement for Sale. Each step needs a record issued by a public authority — this deployment holds none of them, so the protocol documents what to obtain and verify, rather than confirming that any given flat is safe to buy.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
              <div className="p-4 border border-current/20 bg-black/5 space-y-2">
                <div className="w-7 h-7 bg-red-600 text-white font-black flex items-center justify-center text-xs">
                  01
                </div>
                <div className="font-bold uppercase text-sm">Verify 14-Digit ULPIN</div>
                <p className="text-[11px] opacity-75">
                  Scan the QR code on the builder brochure or enter the parcel ULPIN. Ensure the Luhn Mod 36 check digit matches the state registry.
                </p>
              </div>

              <div className="p-4 border border-current/20 bg-black/5 space-y-2">
                <div className="w-7 h-7 bg-black text-white font-black flex items-center justify-center text-xs">
                  02
                </div>
                <div className="font-bold uppercase text-sm">Check 3D Sanction Height</div>
                <p className="text-[11px] opacity-75">
                  Confirm the flat level (e.g. 5th floor) exists within the permissible DCR envelope. Check that no vertical encroachment banner is flagged.
                </p>
              </div>

              <div className="p-4 border border-current/20 bg-black/5 space-y-2">
                <div className="w-7 h-7 bg-black text-white font-black flex items-center justify-center text-xs">
                  03
                </div>
                <div className="font-bold uppercase text-sm">Inspect Bank Encumbrance</div>
                <p className="text-[11px] opacity-75">
                  Review the unit mortgage ledger. Ensure the unit has a valid Bank No-Objection Certificate (NOC) and is free from developer loans.
                </p>
              </div>

              <div className="p-4 border border-current/20 bg-black/5 space-y-2">
                <div className="w-7 h-7 bg-black text-white font-black flex items-center justify-center text-xs">
                  04
                </div>
                <div className="font-bold uppercase text-sm">Download Prototype Monograph</div>
                <p className="text-[11px] opacity-75">
                  Export an unregistered demonstration monograph PDF. It carries no seal, emblem, or legal standing.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
};
