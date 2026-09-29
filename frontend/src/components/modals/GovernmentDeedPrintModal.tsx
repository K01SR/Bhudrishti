import React, { useRef } from 'react';
import { X, Printer, Download, FileText, ShieldCheck, QrCode, Award, Layers } from 'lucide-react';
import { HeroProperty } from '../../types/cadastre';
import { PROPERTY_CARD_PDF_URL, PROPERTY_CARD_LATEX_URL, CADASTRAL_EXCEL_URL } from '../../services/api';

interface Props {
  property: HeroProperty;
  isOpen: boolean;
  onClose: () => void;
}

export const GovernmentDeedPrintModal: React.FC<Props> = ({ property, isOpen, onClose }) => {
  const printRef = useRef<HTMLDivElement>(null);

  if (!isOpen) return null;

  const handlePrint = () => {
    window.print();
  };

  // A deed is a legal instrument about one specific parcel. The fallback
  // printed every deed for a parcel that has no record, against ULPIN
  // 12345678901234, which belongs to a real cadastral entry. Without a real
  // parent ULPIN there is nothing to print.
  const ulpin = property.parent_ulpin;
  if (!ulpin) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
        <div className="max-w-md bg-white border-2 border-ink p-6">
          <p className="font-bold text-ink">No deed can be generated</p>
          <p className="text-sm text-ink-soft mt-2">
            This property has no cadastral record, so there is no parent ULPIN to print
            against. A deed is a legal document about a specific parcel; generating one
            with an invented identifier would fabricate a land record.
          </p>
          <button
            onClick={onClose}
            className="mt-4 px-4 py-2 bg-slate-900 text-white text-sm font-bold"
          >
            Close
          </button>
        </div>
      </div>
    );
  }
  const s = property.structure || {};
  const units = (s as any).units || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/70 backdrop-blur-md animate-rise-in">
      <div className="relative w-full max-w-5xl max-h-[96vh] bg-canvas rounded-none shadow-brutal-xl border-2 border-ink flex flex-col overflow-hidden">
        {/* Modal Action Header (Excluded in print) */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-3.5 bg-slate-900 text-white border-b border-slate-800 print:hidden">
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-none bg-ink/30 text-ink-mut border-2 border-ink">
              <Award className="w-5 h-5" />
            </span>
            <div>
              <h3 className="font-bold text-sm tracking-wide text-white flex items-center gap-2">
                3D Cadastral Monograph &amp; Technical Notes
                <span className="text-[10px] font-mono uppercase bg-emerald-500/20 text-emerald-300 border-2 border-emerald-500/30 px-2 py-0.5 rounded-none">
                  Unregistered prototype output
                </span>
              </h3>
              <p className="text-[11px] text-ink-soft font-mono">
                Academic prototype — not a deed, not gazetted, not issued by any authority
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handlePrint}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-none text-xs font-bold text-white bg-ink hover:bg-ink shadow-brutal-sm transition"
              title="Open browser print preview (Formatted for A4 PDF export)"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print / Save PDF</span>
            </button>

            <a
              href={PROPERTY_CARD_PDF_URL(ulpin)}
              download={`Bhu_Drishti_3D_Property_Card_${ulpin}.pdf`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-ink-mut bg-slate-800 hover:bg-slate-700 border-2 border-slate-700 transition"
              title="Download compiled Vector PDF generated via ReportLab"
            >
              <Download className="w-3.5 h-3.5 text-ink-mut" />
              <span>Vector PDF</span>
            </a>

            <a
              href={PROPERTY_CARD_LATEX_URL(ulpin)}
              download={`Bhu_Drishti_3D_Deed_${ulpin}.tex`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-ink-mut bg-slate-800 hover:bg-slate-700 border-2 border-slate-700 transition"
              title="Download full LaTeX source code (.tex) ready for Overleaf / TeXLive compilation"
            >
              <FileText className="w-3.5 h-3.5 text-amber-400" />
              <span>LaTeX (.tex)</span>
            </a>

            <a
              href={CADASTRAL_EXCEL_URL}
              download="Bhu_Drishti_Cadastral_Register.xlsx"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-ink-mut bg-slate-800 hover:bg-slate-700 border-2 border-slate-700 transition"
              title="Download full multi-tab Cadastral Workbook (.xlsx)"
            >
              <Layers className="w-3.5 h-3.5 text-emerald-400" />
              <span>Excel (.xlsx)</span>
            </a>

            <button
              onClick={onClose}
              className="p-1.5 rounded-none text-ink-soft hover:text-white hover:bg-slate-800 transition ml-2"
              aria-label="Close dialog"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Container with the Printable Document */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-8 bg-canvas">
          <div
            id="government-deed-dossier"
            ref={printRef}
            className="max-w-4xl mx-auto bg-white border-2 border-ink shadow-brutal-lg p-8 sm:p-14 text-ink space-y-12 font-serif print:p-0 print:border-none print:shadow-none print:max-w-none"
          >
            {/* ============================================================= */}
            {/* PAGE 1: TITLE PAGE / SOVEREIGN CADASTRAL COVER                */}
            {/* ============================================================= */}
            <div className="min-h-[850px] flex flex-col justify-between border-b-2 border-ink pb-12 print:border-none print:pb-0">
              <div className="text-center space-y-3">
                {/* State Emblem & Crest */}
                <div className="inline-flex flex-col items-center justify-center p-3 rounded-none border-2 border-ink bg-accent-faint mb-2">
                  <div className="w-16 h-16 rounded-none border-2 border-dashed border-amber-600 flex items-center justify-center text-ink text-2xl font-black">
                    
                  </div>
                  <span className="text-[10px] font-bold text-ink tracking-widest mt-1 uppercase">
                    शासकीय महाभूमी
                  </span>
                </div>

                <h1 className="text-xl sm:text-2xl font-black tracking-widest text-ink uppercase">
                  BHU-DRISHTI 3D — RESEARCH PROTOTYPE
                </h1>
                <p className="text-xs sm:text-sm font-bold tracking-widest text-ink uppercase">
                  NOT A GOVERNMENT DEPARTMENT — NOT AN OFFICIAL DOCUMENT
                </p>
                <p className="text-xs text-ink-soft font-sans">
                  Academic demonstration output, generated in-browser. No authority issued or
                  endorsed any part of it.
                </p>

                <div className="w-3/4 mx-auto border-t-2 border-ink my-4" />

                <div className="space-y-2 pt-2">
                  <span className="inline-block text-[11px] font-sans font-bold uppercase tracking-widest px-3 py-1 bg-accent-faint text-ink rounded-none">
                    Unregistered demonstration sheet // not Form 3D-ULPIN
                  </span>
                  <h2 className="text-2xl sm:text-3xl font-black text-ink tracking-tight leading-tight">
                    3D VOLUMETRIC CADASTRAL MONOGRAPH
                  </h2>
                  <p className="text-sm sm:text-base font-bold italic text-ink">
                    Stratified Spatial Stratum Specification
                  </p>
                  <p className="text-xs text-ink-soft font-sans">
                    Geographic Parcel: Sector 8, Airoli, Navi Mumbai, District Thane (CTS 142/A, Plot 42)
                  </p>
                </div>
              </div>

              {/* Central ULPIN Banner with QR Code */}
              <div className="my-8 p-6 bg-canvas border-2 border-ink rounded-none flex flex-col sm:flex-row items-center justify-between gap-6 font-sans">
                <div className="space-y-2 text-left">
                  <span className="text-xs font-bold text-ink-soft uppercase tracking-widest block">
                    Demo parent parcel identifier (synthetic, not a ULPIN):
                  </span>
                  <div className="text-2xl sm:text-3xl font-mono font-black text-ink tracking-widest">
                    {ulpin}
                  </div>
                  <div className="text-xs text-ink-soft space-y-0.5">
                    <div><strong>Cadastral Datum:</strong> WGS 84 / UTM Zone 43N (EPSG:32643)</div>
                    <div><strong>Vertical datum:</strong> synthetic local origin &mdash; not tied to GTS or any survey benchmark</div>
                    <div><strong>Ledger Integrity:</strong> <span className="text-ink font-bold">SHA-256 hash chain over this prototype&apos;s own sample records</span></div>
                  </div>
                </div>

                <div className="text-center p-3 bg-white border-2 border-ink rounded-none shadow-brutal-sm">
                  <div className="w-24 h-24 bg-canvas flex items-center justify-center text-ink border-2 border-ink rounded-none">
                    <QrCode className="w-20 h-20 text-ink" />
                  </div>
                  <span className="text-[9px] font-mono text-ink-soft mt-1 block">Prototype reference, not a chain proof</span>
                </div>
              </div>

              {/* Authority & Statutes footer on Title Page */}
              <div className="grid grid-cols-2 gap-4 text-xs font-sans border-t border-ink pt-6">
                <div>
                  <strong className="block text-ink">Produced by:</strong>
                  <span className="text-ink-soft block">Bhu-Drishti 3D, a research prototype</span>
                  <span className="text-ink-soft block">No authoring authority</span>
                  <span className="text-ink-soft block">No attesting or reviewing officer</span>
                </div>
                <div className="text-right">
                  <strong className="block text-ink">Statutory standing:</strong>
                  <span className="text-ink-soft block">None. No statute is applied as authority.</span>
                  <span className="text-ink-soft block">Not registered under any enactment</span>
                  <span className="text-ink-soft block">No standard compliance is claimed</span>
                </div>
              </div>
            </div>

            {/* ============================================================= */}
            {/* CERTIFICATE OF GAZETTED ENDORSEMENT                           */}
            {/* ============================================================= */}
            <div className="print:break-before-page pt-4 space-y-6">
              <div className="text-center space-y-1">
                <h3 className="text-lg font-black uppercase tracking-widest text-ink">
                  Scope and Limitations of this Document
                </h3>
                <p className="text-xs italic text-ink-soft font-sans">
                  Not a gazetted instrument, and no seal of any authority is affixed
                </p>
              </div>

              <div className="p-5 bg-amber-50/40 border-2 border-ink rounded-none text-xs leading-relaxed font-sans text-ink space-y-3">
                <p>
                  This sheet describes the prototype&apos;s rendering of a volumetric parcel with Base
                  ULPIN <strong className="font-mono text-ink">{ulpin}</strong>, labelled{' '}
                  <strong>{s.name || 'Shree Ganesh CHS (Building B-17)'}</strong> in the demonstration
                  dataset at Sector 8, Airoli, Navi Mumbai. The geometry is generated and illustrative.
                  No LiDAR survey, utility clash detection or cadastral reconciliation was performed, and
                  no authority of the Government of Maharashtra or any other body assessed, approved or
                  acted on it.
                </p>
                <p>
                  The figures below come from a seeded demonstration ledger. The hash chain records the
                  order in which this prototype wrote its own sample records. It is not anchored to any
                  external register, and there is no multi-party consensus, no registration and no
                  enforceable title represented here.
                </p>
              </div>

              {/* No signature block. This previously printed "Sd/-" above
                  two named officials, one of them a real serving officer
                  ("Dr. P. K. Deshmukh, IAS, Settlement Commissioner & Director
                  of Land Records, Pune"), either side of a "Sovereign State
                  Seal — Validated" disc. Rendering a named civil servant's
                  signature and a state seal on a document nobody authorised is
                  forgery, so the block is replaced by the absence of one. */}
              <div className="pt-4 border-b border-ink pb-8 text-center font-sans">
                <p className="text-xs text-ink leading-relaxed max-w-xl mx-auto">
                  This document is unsigned. No officer, registrar, notary or
                  government official has signed, sealed, attested or approved
                  it, and no such approval exists. It cannot serve as a deed, a
                  title document, a sanad or evidence of ownership.
                </p>
              </div>
            </div>

            {/* ============================================================= */}
            {/* EXECUTIVE SUMMARY & TECHNICAL ABSTRACT                        */}
            {/* ============================================================= */}
            <div className="space-y-4">
              <h3 className="text-base font-black uppercase tracking-widest text-ink">
                Executive Summary & Spatial Abstract
              </h3>
              <p className="text-xs font-sans leading-relaxed text-ink text-justify">
                This monograph is a prototype printout for a synthetic building in Sector 8, Airoli, Navi Mumbai. It
                is not issued under the Maharashtra Land Revenue Code, it has not been tested against ISO 19152, and it
                has no legal standing. The geometry shown is a massing model generated in the browser from the
                demo dataset, with a local vertical origin that is not tied to GTS or any survey benchmark. No LiDAR
                point cloud and no municipal sanction plan were read, and the Floor Space Index figure is a value
                entered in the builder form rather than a verified FSI. Nothing on this sheet records a setback,
                overhang or encroachment finding.
              </p>
            </div>

            {/* ============================================================= */}
            {/* CHAPTER 1: GEODETIC SPATIAL ENVELOPE                          */}
            {/* ============================================================= */}
            <div className="print:break-before-page pt-4 space-y-4">
              <div className="border-b-2 border-slate-900 pb-1">
                <h3 className="text-base font-black uppercase tracking-wide text-ink">
                  Chapter 1: Geodetic Spatial Envelope & Site Boundary Geometry
                </h3>
              </div>

              <div className="font-sans text-xs space-y-4">
                <p className="text-ink">
                  All coordinates and spatial geometries reference Universal Transverse Mercator (UTM) Zone 43 North
                  (EPSG:32643) based on WGS 84. Vertical elevations use a synthetic local origin for this
                  demo and are not tied to the Great Trigonometrical Survey datum or any survey benchmark.
                </p>

                {/* Massing Specifications Table */}
                <table className="w-full text-xs border-2 border-ink">
                  <tbody className="divide-y divide-slate-200">
                    <tr className="bg-canvas">
                      <td className="p-2 font-bold text-ink w-1/4">Property Designation</td>
                      <td className="p-2 text-ink w-1/4">{s.name || 'Shree Ganesh CHS'}</td>
                      <td className="p-2 font-bold text-ink w-1/4">Building Code</td>
                      <td className="p-2 text-ink font-mono w-1/4">{s.building_code || 'B-17'}</td>
                    </tr>
                    <tr>
                      <td className="p-2 font-bold text-ink">Survey / CTS No.</td>
                      <td className="p-2 text-ink">CTS 142/A, Plot No. 42</td>
                      <td className="p-2 font-bold text-ink">Sector / Locality</td>
                      <td className="p-2 text-ink">Airoli Sector 8, Navi Mumbai</td>
                    </tr>
                    <tr className="bg-canvas">
                      <td className="p-2 font-bold text-ink">Reference locality</td>
                      <td className="p-2 text-ink">Airoli Sector 8 (demo setting)</td>
                      <td className="p-2 font-bold text-ink">MahaRERA registration</td>
                      <td className="p-2 text-ink font-mono">Not looked up</td>
                    </tr>
                    <tr>
                      <td className="p-2 font-bold text-ink">Above-Ground Storeys</td>
                      <td className="p-2 text-ink">{s.floors_count || 5} Storeys (Ground + 4 Upper)</td>
                      <td className="p-2 font-bold text-ink">Basements Count</td>
                      <td className="p-2 text-ink">{s.basements_count || 1} Level (B1 Subsurface)</td>
                    </tr>
                    <tr className="bg-canvas">
                      <td className="p-2 font-bold text-ink">Total Measured Height</td>
                      <td className="p-2 text-ink font-mono">{s.height_m || 18.0} meters</td>
                      <td className="p-2 font-bold text-ink">Ground Footprint Area</td>
                      <td className="p-2 text-ink font-mono">510.00 sq. meters</td>
                    </tr>
                    <tr>
                      <td className="p-2 font-bold text-ink">Total Built-Up Area</td>
                      <td className="p-2 text-ink font-mono">{s.total_built_up_area_m2 || 2550.0} sq. meters</td>
                      <td className="p-2 font-bold text-ink">Permissible / Actual FSI</td>
                      <td className="p-2 text-ink font-mono font-bold text-emerald-700">1.80 / Max 2.00 (PASS)</td>
                    </tr>
                    <tr className="bg-canvas">
                      <td className="p-2 font-bold text-ink">Geodetic Centroid</td>
                      <td className="p-2 text-ink font-mono">19.155372° N, 72.998024° E</td>
                      <td className="p-2 font-bold text-ink">NBC Seismic Rating</td>
                      <td className="p-2 text-ink">Zone III (IS 1893:2016 Compliant)</td>
                    </tr>
                  </tbody>
                </table>

                {/* Boundary Traverse Table */}
                <div className="pt-2">
                  <h4 className="font-bold text-ink uppercase text-[11px] mb-1">
                    Boundary Traverse Coordinates (EPSG:32643)
                  </h4>
                  <table className="w-full text-[11px] border-2 border-ink">
                    <thead className="bg-slate-900 text-white">
                      <tr>
                        <th className="p-1.5 text-left">Vertex ID</th>
                        <th className="p-1.5 text-right font-mono">Easting (m)</th>
                        <th className="p-1.5 text-right font-mono">Northing (m)</th>
                        <th className="p-1.5 text-right font-mono">Elevation (Z, local origin)</th>
                        <th className="p-1.5 text-right font-mono">Segment</th>
                        <th className="p-1.5 text-left">Boundary Adjoining</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 font-mono text-[10px]">
                      <tr>
                        <td className="p-1.5 font-sans font-bold">P-01 (NW)</td>
                        <td className="p-1.5 text-right">298145.000</td>
                        <td className="p-1.5 text-right">2113544.000</td>
                        <td className="p-1.5 text-right">+12.000m</td>
                        <td className="p-1.5 text-right font-bold">30.00m</td>
                        <td className="p-1.5 font-sans">18m Municipal Road</td>
                      </tr>
                      <tr className="bg-canvas">
                        <td className="p-1.5 font-sans font-bold">P-02 (NE)</td>
                        <td className="p-1.5 text-right">298175.000</td>
                        <td className="p-1.5 text-right">2113544.000</td>
                        <td className="p-1.5 text-right">+12.050m</td>
                        <td className="p-1.5 text-right font-bold">17.00m</td>
                        <td className="p-1.5 font-sans">CTS 142/B (Residential)</td>
                      </tr>
                      <tr>
                        <td className="p-1.5 font-sans font-bold">P-03 (SE)</td>
                        <td className="p-1.5 text-right">298175.000</td>
                        <td className="p-1.5 text-right">2113561.000</td>
                        <td className="p-1.5 text-right">+11.950m</td>
                        <td className="p-1.5 text-right font-bold">30.00m</td>
                        <td className="p-1.5 font-sans">CTS 143/A (Commercial)</td>
                      </tr>
                      <tr className="bg-canvas">
                        <td className="p-1.5 font-sans font-bold">P-04 (SW)</td>
                        <td className="p-1.5 text-right">298145.000</td>
                        <td className="p-1.5 text-right">2113561.000</td>
                        <td className="p-1.5 text-right">+11.900m</td>
                        <td className="p-1.5 text-right font-bold">17.00m</td>
                        <td className="p-1.5 font-sans">Internal Society Pathway</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* ============================================================= */}
            {/* CHAPTER 2: STRATIFIED 3D VOLUMETRIC UNITS REGISTER            */}
            {/* ============================================================= */}
            <div className="print:break-before-page pt-4 space-y-4">
              <div className="border-b-2 border-slate-900 pb-1">
                <h3 className="text-base font-black uppercase tracking-wide text-ink">
                  Chapter 2: Stratified 3D Spatial Units Register (ISO/IEC 7064 Luhn Mod 36)
                </h3>
              </div>

              <div className="font-sans text-xs space-y-3">
                <p className="text-ink">
                  Pursuant to MLRC 1966 Section 148A, land records are segmented into 3D volumetric units along the
                  vertical Z-axis. Each unit comprises an enclosed polyhedral space bounded by elevations (Z_min, Z_max),
                  carpet area, and air volume:
                </p>

                <table className="w-full text-xs border-2 border-ink">
                  <thead className="bg-ink text-white font-bold text-[10px]">
                    <tr>
                      <th className="p-2 text-left">Proposed 3D-ULPIN</th>
                      <th className="p-2 text-center">Lvl</th>
                      <th className="p-2 text-center">Unit</th>
                      <th className="p-2 text-right">Carpet</th>
                      <th className="p-2 text-right">Vol (m³)</th>
                      <th className="p-2 text-left">Registered Title Holder</th>
                      <th className="p-2 text-center">Encumbrance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 font-mono text-[10px]">
                    {units.slice(0, 10).map((u: any, idx: number) => {
                      const rights = (u.rights && u.rights[0]) || {};
                      const owner = rights.party_name || 'Rajesh Sharma';
                      const enc = rights.encumbrance_status || 'CLEAR';
                      return (
                        <tr key={idx} className={idx % 2 === 1 ? 'bg-canvas' : 'bg-white'}>
                          <td className="p-1.5 font-bold text-ink">{u.proposed_3d_id}</td>
                          <td className="p-1.5 text-center font-sans">{u.level_code}</td>
                          <td className="p-1.5 text-center font-sans">{u.unit_number}</td>
                          <td className="p-1.5 text-right">{u.carpet_area_m2?.toFixed(1)} m²</td>
                          <td className="p-1.5 text-right">{u.volume_m3?.toFixed(1)}</td>
                          <td className="p-1.5 font-sans font-bold text-ink">{owner}</td>
                          <td className="p-1.5 text-center font-sans">
                            <span className={`px-1.5 py-0.5 rounded-none text-[9px] font-bold ${
                              enc === 'CLEAR' ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                            }`}>
                              {enc}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* ============================================================= */}
            {/* CHAPTER 3: BLOCKCHAIN PROOF & CRYPTOGRAPHIC LEDGER            */}
            {/* ============================================================= */}
            <div className="print:break-before-page pt-4 space-y-4">
              <div className="border-b-2 border-slate-900 pb-1">
                <h3 className="text-base font-black uppercase tracking-wide text-ink">
                  Chapter 3: Tamper-Evident Cadastral Blockchain Cryptographic Proof
                </h3>
              </div>

              <div className="font-sans text-xs space-y-4">
                <div className="p-4 bg-slate-900 text-white rounded-none border-2 border-slate-800 space-y-2">
                  <div className="flex items-center gap-2 text-emerald-400 font-bold text-xs uppercase tracking-widest">
                    <ShieldCheck className="w-4 h-4" /> Local Prototype Hash (no blockchain)
                  </div>
                  <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-[11px] pt-1">
                    <div>
                      <span className="text-ink-soft block text-[10px]">Block Height:</span>
                      <span className="font-mono font-bold text-ink-mut">Demo record (no mining performed)</span>
                    </div>
                    <div>
                      <span className="text-ink-soft block text-[10px]">Endorsements:</span>
                      <span className="font-bold text-ink-soft">None — no other party signed or was contacted</span>
                    </div>
                    <div className="col-span-2">
                      <span className="text-ink-soft block text-[10px]">Block SHA-256 Hash:</span>
                      <span className="font-mono text-[9px] text-ink-mut break-all">
                        0000a98f12c841e573db94f61e8093cb4112e8731b816a20d58e3f940b382d56
                      </span>
                    </div>
                    <div className="col-span-2">
                      <span className="text-ink-soft block text-[10px]">Merkle Tree State Root:</span>
                      <span className="font-mono text-[9px] text-amber-300 break-all">
                        7f8a9b2c3d4e5f6a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a
                      </span>
                    </div>
                  </div>
                </div>

                <div className="space-y-1">
                  <h4 className="font-bold text-ink uppercase text-[11px]">
                    Subsurface Utilities &amp; Topology — Not Assessed
                  </h4>
                  <p className="text-ink text-justify">
                    No utility, corridor or overhang check is performed. This prototype loads no water, sewer, power
                    or rail alignment layer, so no buffer distance, clash count or clearance can be measured. The
                    figures previously printed here — a 4.20 m water-main offset, an 82.4 m metro offset, a 0.00 mm
                    overhang and a &ldquo;2.00 m statutory buffer&rdquo; — were typed in by hand and described checks
                    that do not exist.
                  </p>
                </div>
              </div>
            </div>

            {/* ============================================================= */}
            {/* CHAPTER 4: STATUTORY REFERENCES & LEGAL ACTS                  */}
            {/* ============================================================= */}
            <div className="pt-4 space-y-4 border-t border-ink">
              <h3 className="text-sm font-black uppercase tracking-widest text-ink">
                Standards Consulted (not applied as legal authority)
              </h3>
              <p className="text-xs font-sans text-ink-soft">
                Listed because the prototype&apos;s data model borrows their vocabulary. No provision
                of any of these instruments has been applied, tested or certified here, and citing them
                does not make this sheet compliant with them.
              </p>
              <ol className="list-decimal list-inside text-xs font-sans space-y-1 text-ink-soft">
                <li>Government of Maharashtra (1966). <em>The Maharashtra Land Revenue Code, 1966 (Mah. XLI of 1966)</em>, Sections 148, 148A.</li>
                <li>Government of India (2016). <em>The Real Estate (Regulation and Development) Act, 2016 (MahaRERA)</em>.</li>
                <li>Bureau of Indian Standards (2016). <em>National Building Code of India 2016 (SP:7)</em>, Development Control Regulations.</li>
                <li>International Organization for Standardization (2012). <em>ISO 19152:2012 Land Administration Domain Model (LADM)</em>.</li>
                <li>ISO/IEC (2008). <em>ISO/IEC 7064: Information Technology — Check Character Systems (Mod 36, 36)</em>.</li>
              </ol>

              <div className="text-center pt-8 border-t border-ink">
                <span className="text-[10px] font-mono text-ink-soft uppercase tracking-widest">
                  *** END OF UNREGISTERED DEMONSTRATION SHEET ***
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
