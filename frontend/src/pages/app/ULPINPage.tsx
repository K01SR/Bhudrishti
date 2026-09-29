import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  QrCode,
  Info,
  Calculator,
  Dices,
  CheckCircle2,
  Copy,
  Building2,
  Search,
  ShieldCheck,
  Check,
  Sparkles,
  Loader2,
  FileSpreadsheet,
  Upload,
  Download,
  Globe2,
  Compass,
  Layers,
  X,
} from 'lucide-react';
import {
  decode3DID,
  generate3DID,
  fetchPrecinct3DIDs,
  Precinct3DBuilding,
  fetchUnextrudedParcels,
  extrudeAll2DParcels,
  extrudeSingleParcel,
  UnextrudedParcel,
  ExtrudeAllResponse,
  generate3dFromSpreadsheet,
  EXCEL_TEMPLATE_URL,
  CSV_TEMPLATE_URL,
  fetchNationalUlpinSpec,
  deriveNationalUlpin,
  verifyNationalUlpin,
  verifyStoredNationalParcel,
  extrudeNationalParcelTwin,
  extrudeNationalBoundaryTwins,
  PROPERTY_CARD_PDF_URL,
} from '../../services/api';
import { SpreadsheetExtrusionResponse } from '../../types/cadastre';
import { Card, Button, Field, Badge, DemoHint, StatusBadge } from '../../components/ui';
import { useApp } from '../../context/AppContext';
import { DEMO_ULPIN } from '../../constants';

export const ULPINPage: React.FC = () => {
  const { showToast } = useApp();
  const [inputID, setInputID] = useState(`${DEMO_ULPIN}/UB17-L05-501-U`);
  const [decoded, setDecoded] = useState<any | null>(null);
  const [decoding, setDecoding] = useState(false);
  const [decodeError, setDecodeError] = useState<string | null>(null);

  const [gen, setGen] = useState({ parent_ulpin: DEMO_ULPIN, type_code: 'U', building_code: 'B17', level_code: 'L02', unit_code: '201' });
  const [generated, setGenerated] = useState<any | null>(null);
  const [generating, setGenerating] = useState(false);

  // Precinct 3D-ULPIN Explorer state
  const [buildings, setBuildings] = useState<Precinct3DBuilding[]>([]);
  // Totals come from the API rather than being written into this page, so the
  // copy cannot drift from the catalogue it describes.
  const [catalogueTotals, setCatalogueTotals] = useState<{ total_3d_ids: number; total_buildings: number }>({
    total_3d_ids: 0,
    total_buildings: 0,
  });
  const [selectedCode, setSelectedCode] = useState<string>('B-17');
  const [unitSearch, setUnitSearch] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<'ALL' | 'U' | 'C' | 'P' | 'A'>('ALL');
  const [, setLoadingPrecinct] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // 2D to 3D Extrusion state
  const [unextruded, setUnextruded] = useState<UnextrudedParcel[]>([]);
  const [, setLoadingUnextruded] = useState(true);
  const [extrudingAll, setExtrudingAll] = useState(false);
  const [extrudingSingle, setExtrudingSingle] = useState<string | null>(null);
  const [extrusionReport, setExtrusionReport] = useState<ExtrudeAllResponse | null>(null);

  // Active Tab state
  const [activeTab, setActiveTab] = useState<'NATIONAL' | 'EXTRUSION' | 'PRECINCT' | 'SPREADSHEET' | 'DECODER'>('NATIONAL');

  // Parcel identifier & Twin Engine state
  const [nationalSpec, setNationalSpec] = useState<any | null>(null);
  const [specModalOpen, setSpecModalOpen] = useState(false);
  const [nationalUlpinInput, setNationalUlpinInput] = useState('EFI7V44HUACG2U');
  const [verifiedParcel, setVerifiedParcel] = useState<any | null>(null);
  const [verifyingParcel, setVerifyingParcel] = useState(false);

  const [ringInput, setRingInput] = useState(
    JSON.stringify(
      [
        [19.1550, 72.9980],
        [19.1565, 72.9980],
        [19.1565, 72.9995],
        [19.1550, 72.9995],
        [19.1550, 72.9980],
      ],
      null,
      2
    )
  );
  const [derivedResult, setDerivedResult] = useState<any | null>(null);
  const [deriving, setDeriving] = useState(false);

  const [extrudingNational, setExtrudingNational] = useState(false);
  const [nationalTwinResult, setNationalTwinResult] = useState<any | null>(null);

  const [boundaryCodeInput, setBoundaryCodeInput] = useState('MH-THANE-T-01-V-01');
  const [extrudingBoundary, setExtrudingBoundary] = useState(false);
  const [boundaryExtrudeResult, setBoundaryExtrudeResult] = useState<any | null>(null);

  // Excel / CSV 3D ULPIN Studio state
  const [spreadsheetFile, setSpreadsheetFile] = useState<File | null>(null);
  const [processingSpreadsheet, setProcessingSpreadsheet] = useState(false);
  const [spreadsheetResult, setSpreadsheetResult] = useState<SpreadsheetExtrusionResponse | null>(null);

  const handleSpreadsheetFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSpreadsheetFile(e.target.files[0]);
    }
  };

  const handleProcessSpreadsheet = async () => {
    if (!spreadsheetFile) return;
    setProcessingSpreadsheet(true);
    try {
      const res = await generate3dFromSpreadsheet(spreadsheetFile);
      setSpreadsheetResult(res);
      showToast(`Successfully extruded ${res.total_buildings_generated} buildings & ${res.total_3d_ulpins_minted} 3D-ULPINs!`);
      loadData();
    } catch (e: any) {
      showToast(e.message || 'Spreadsheet processing failed');
    } finally {
      setProcessingSpreadsheet(false);
    }
  };

  const loadData = useCallback(() => {
    fetchPrecinct3DIDs()
      .then((data) => {
        setBuildings(data.buildings || []);
        setCatalogueTotals({
          total_3d_ids: data.total_3d_ids || 0,
          total_buildings: data.total_buildings || 0,
        });
        setLoadingPrecinct(false);
      })
      .catch((err) => {
        console.error('Failed to load precinct 3D IDs', err);
        setLoadingPrecinct(false);
      });

    fetchUnextrudedParcels()
      .then((data) => {
        setUnextruded(data.parcels || []);
        setLoadingUnextruded(false);
      })
      .catch((err) => {
        console.error('Failed to load unextruded parcels', err);
        setLoadingUnextruded(false);
      });
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleVerifyStoredParcel = async (ulpinToTest?: string) => {
    const target = (ulpinToTest || nationalUlpinInput).trim();
    if (!target) return;
    setVerifyingParcel(true);
    setVerifiedParcel(null);
    try {
      const res = await verifyStoredNationalParcel(target);
      setVerifiedParcel(res);
      showToast(`Parcel ${target} checksum: ${res.valid ? 'MATCH' : 'MISMATCH'}`);
    } catch (e: any) {
      showToast(e.message || 'Parcel verification failed');
    } finally {
      setVerifyingParcel(false);
    }
  };

  const handleDeriveRing = async () => {
    setDeriving(true);
    setDerivedResult(null);
    try {
      const parsedRing = JSON.parse(ringInput);
      const res = await deriveNationalUlpin({ ring: parsedRing });
      setDerivedResult(res);
      showToast(`Derived ULPIN: ${res.ulpin}`);
    } catch (e: any) {
      showToast(e.message || 'Ring derivation failed');
    } finally {
      setDeriving(false);
    }
  };

  const handleVerifyRing = async () => {
    setDeriving(true);
    try {
      const parsedRing = JSON.parse(ringInput);
      const res = await verifyNationalUlpin({ ring: parsedRing, ulpin: nationalUlpinInput });
      setDerivedResult(res);
      showToast(`Ring vs ULPIN match: ${res.valid ? 'VERIFIED' : 'MISMATCH'}`);
    } catch (e: any) {
      showToast(e.message || 'Ring verification failed');
    } finally {
      setDeriving(false);
    }
  };

  const handleExtrudeNationalTwin = async () => {
    if (!nationalUlpinInput.trim()) return;
    setExtrudingNational(true);
    try {
      const res = await extrudeNationalParcelTwin(nationalUlpinInput.trim());
      setNationalTwinResult(res);
      showToast(`3D Twin extruded for ${nationalUlpinInput}!`);
    } catch (e: any) {
      showToast(e.message || 'Extrusion failed');
    } finally {
      setExtrudingNational(false);
    }
  };

  const handleExtrudeBoundaryTwins = async () => {
    if (!boundaryCodeInput.trim()) return;
    setExtrudingBoundary(true);
    try {
      const res = await extrudeNationalBoundaryTwins(boundaryCodeInput.trim());
      setBoundaryExtrudeResult(res);
      showToast(`Extruded twins for boundary ${boundaryCodeInput}!`);
    } catch (e: any) {
      showToast(e.message || 'Boundary extrusion failed');
    } finally {
      setExtrudingBoundary(false);
    }
  };

  const handleOpenNationalSpec = async () => {
    setSpecModalOpen(true);
    if (!nationalSpec) {
      try {
        const spec = await fetchNationalUlpinSpec();
        setNationalSpec(spec);
      } catch (e) {
        console.error('Failed to fetch national spec', e);
      }
    }
  };

  const handleExtrudeAll = async () => {
    setExtrudingAll(true);
    setExtrusionReport(null);
    try {
      const res = await extrudeAll2DParcels();
      setExtrusionReport(res);
      showToast(res.message);
      loadData();
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Batch extrusion failed');
    } finally {
      setExtrudingAll(false);
    }
  };

  const handleExtrudeSingle = async (ulpin: string) => {
    setExtrudingSingle(ulpin);
    try {
      const res = await extrudeSingleParcel(ulpin);
      showToast(res.message);
      loadData();
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Single parcel extrusion failed');
    } finally {
      setExtrudingSingle(null);
    }
  };

  const handleDecode = async (val?: string) => {
    const target = (val || inputID).trim();
    if (!target) return;
    setDecoding(true);
    setDecodeError(null);
    setDecoded(null);
    try {
      setDecoded(await decode3DID(target));
    } catch (e) {
      setDecodeError(e instanceof Error ? e.message : 'Decode failed');
    } finally {
      setDecoding(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setGenerated(null);
    try {
      const res = await generate3DID(gen);
      setGenerated(res);
      showToast('3D-ID generated — deterministic, no collisions');
    } catch (e) {
      setDecodeError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const examples = [
    `${DEMO_ULPIN}/UB17-L05-501-U`,
    `${DEMO_ULPIN}/SB17-B1-104-P`,
    '20260925000001/UB01-G-001-O',
    '20260925000003/PB03-B1-P01-4',
  ];

  const copy = (t: string) => {
    navigator.clipboard?.writeText(t).catch(() => {});
    setCopiedId(t);
    setTimeout(() => setCopiedId(null), 2000);
    showToast('Copied to clipboard');
  };

  const selectedBuilding = useMemo(() => {
    return buildings.find((b) => b.code === selectedCode) || buildings[0];
  }, [buildings, selectedCode]);

  const filteredUnits = useMemo(() => {
    if (!selectedBuilding?.units) return [];
    let list = selectedBuilding.units;
    if (typeFilter !== 'ALL') {
      list = list.filter((u) => u.unit_type === typeFilter);
    }
    if (unitSearch.trim()) {
      const q = unitSearch.trim().toLowerCase();
      list = list.filter(
        (u) =>
          u.unit_number.toLowerCase().includes(q) ||
          u.level_code.toLowerCase().includes(q) ||
          u.proposed_3d_id.toLowerCase().includes(q)
      );
    }
    return list;
  }, [selectedBuilding, typeFilter, unitSearch]);

  // Count the units that were actually emitted, not the separately maintained
  // `units_count` metadata. Those two disagree whenever a record carries no
  // unit list but still carries a stored count, which made this page print two
  // different precinct totals on the same screen.
  const unitCount = useCallback(
    (b: { units?: unknown[] | null; units_count?: number | null } | undefined | null) =>
      b?.units?.length ?? b?.units_count ?? 0,
    []
  );

  const totalPrecinctUnits = useMemo(() => {
    return buildings.reduce((acc, b) => acc + unitCount(b), 0);
  }, [buildings, unitCount]);

  const verifyInEngine = (id: string) => {
    setInputID(id);
    handleDecode(id);
    window.scrollTo({ top: 120, behavior: 'smooth' });
    showToast(`Loaded ${id} into verification decoder`);
  };

  const copyAllForBuilding = () => {
    if (!selectedBuilding?.units) return;
    const lines = [
      `# 3D ULPIN Registry Export — ${selectedBuilding.name} (${selectedBuilding.code})`,
      `# Parent ULPIN: ${selectedBuilding.parent_ulpin}`,
      `# Building 3D-ID: ${selectedBuilding.building_3d_id || 'N/A'}`,
      `# Total Units: ${selectedBuilding.units.length}`,
      'Unit_Number,Level,Type,3D_ULPIN',
      ...selectedBuilding.units.map(
        (u) => `${u.unit_number},${u.level_code},${u.unit_type},${u.proposed_3d_id}`
      ),
    ].join('\n');
    copy(lines);
    showToast(`Copied ${selectedBuilding.units.length} 3D-ULPIN records as CSV`);
  };

  return (
    <div className="flex flex-col gap-6 animate-rise-in">
      <div>
        <div className="flex items-center gap-2 annotation text-accent-strong">
          <span className="text-accent-strong">Identifier Engine</span><span>/</span><span>3D-ID</span>
        </div>
        <h1 className="text-2xl font-black text-ink font-display tracking-tight mt-1">3D-ULPIN Engine & Registry</h1>
        <p className="text-sm text-ink-soft mt-1">
          Deterministic vertical extensions of a 14-digit parent parcel identifier —{' '}
          {catalogueTotals.total_3d_ids || totalPrecinctUnits} spatial units across{' '}
          {catalogueTotals.total_buildings || buildings.length} demo precinct buildings. The parent
          identifier is synthetic; no ULPIN was issued by any authority.
        </p>
      </div>

      <div className="p-4 rounded-none bg-accent-faint border-2 border-ink text-xs text-ink leading-relaxed flex items-start gap-3">
        <Info className="w-5 h-5 text-accent-strong shrink-0 mt-0.5" />
        <div>
          <strong className="font-bold text-ink">How these identifiers are built:</strong>{' '}
          Each 3D identifier anchors to a 14-character parent parcel number that is generated by this
          demo. Vertical segments specify unit type (U = Habitable Unit, C = Commercial Suite, P =
          Parking, A = Air Rights), building code, level, unit number, and a final Luhn Mod 36
          checksum character. That checksum detects transcription errors in an identifier that was
          already generated here. It is not a signature and proves nothing about ownership,
          authenticity, or any real-world property.
        </div>
      </div>

      {/* Top Tab Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink pb-3">
        <div className="flex items-center gap-1.5 overflow-x-auto p-1 bg-canvas border-2 border-ink rounded-none">
          <button
            onClick={() => setActiveTab('NATIONAL')}
            className={`px-3.5 py-2 rounded-none text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === 'NATIONAL'
                ? 'bg-ink text-white shadow-brutal-sm'
                : 'text-ink hover:text-ink hover:bg-canvas'
            }`}
          >
            <Globe2 className="w-3.5 h-3.5" />
            Parcel Identifier Engine
          </button>
          <button
            onClick={() => setActiveTab('EXTRUSION')}
            className={`px-3.5 py-2 rounded-none text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === 'EXTRUSION'
                ? 'bg-accent text-white shadow-brutal-sm'
                : 'text-ink hover:text-ink hover:bg-canvas'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            2D → 3D AI Extrusion ({unextruded.length})
          </button>
          <button
            onClick={() => setActiveTab('PRECINCT')}
            className={`px-3.5 py-2 rounded-none text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === 'PRECINCT'
                ? 'bg-accent text-white shadow-brutal-sm'
                : 'text-ink hover:text-ink hover:bg-canvas'
            }`}
          >
            <Building2 className="w-3.5 h-3.5" />
            Precinct 3D Units ({totalPrecinctUnits})
          </button>
          <button
            onClick={() => setActiveTab('SPREADSHEET')}
            className={`px-3.5 py-2 rounded-none text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === 'SPREADSHEET'
                ? 'bg-emerald-600 text-white shadow-brutal-sm'
                : 'text-ink hover:text-ink hover:bg-canvas'
            }`}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            Excel / CSV 3D Studio
          </button>
          <button
            onClick={() => setActiveTab('DECODER')}
            className={`px-3.5 py-2 rounded-none text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === 'DECODER'
                ? 'bg-ink text-white shadow-brutal-sm'
                : 'text-ink hover:text-ink hover:bg-canvas'
            }`}
          >
            <QrCode className="w-3.5 h-3.5" />
            3D-ID Syntax & Checksum
          </button>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleOpenNationalSpec}
            className="flex items-center gap-1.5 text-xs font-bold"
          >
            <Info className="w-3.5 h-3.5 text-accent-strong" />
            Identifier Scheme Reference
          </Button>
          <DemoHint />
        </div>
      </div>

      {/* ----------------- TAB 1: PARCEL IDENTIFIER & TWIN ENGINE ----------------- */}
      {activeTab === 'NATIONAL' && (
        <div className="space-y-6 animate-rise-in">
          {/* National Stats Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Card className="p-4 border-ink bg-chalk to-white">
              <div className="text-[10px] text-accent-strong font-bold uppercase tracking-widest">Demo Identifiers</div>
              <div className="text-2xl font-black font-mono text-ink mt-1">{catalogueTotals.total_3d_ids || '—'}</div>
              <div className="text-[11px] text-ink-soft">Synthetic 3D identifiers in this demo</div>
            </Card>
            <Card className="p-4 border-ink bg-chalk to-white">
              <div className="text-[10px] text-accent-strong font-bold uppercase tracking-widest">Demo Buildings</div>
              <div className="text-2xl font-black font-mono text-ink mt-1">{catalogueTotals.total_buildings || '—'}</div>
              <div className="text-[11px] text-ink-soft">Structures with 3D twins in this demo</div>
            </Card>
            <Card className="p-4 border-ink bg-chalk to-white">
              <div className="text-[10px] text-emerald-700 font-bold uppercase tracking-widest">Parcels Awaiting Extrusion</div>
              <div className="text-2xl font-black font-mono text-emerald-700 mt-1">{unextruded.length || '—'}</div>
              <div className="text-[11px] text-ink-soft">Demo parcels with no 3D twin yet</div>
            </Card>
            <Card className="p-4 border-ink bg-chalk to-white">
              <div className="text-[10px] text-accent-strong font-bold uppercase tracking-widest">Vector Tile Layer</div>
              <div className="text-2xl font-black font-mono text-accent-strong mt-1">MVT</div>
              <div className="text-[11px] text-ink-soft">PostGIS vector tiles, cached in memory</div>
            </Card>
          </div>

          {/* Section A: Live National Parcel Verification & On-Demand 3D Twin Extruder */}
          <Card className="p-6 border-ink shadow-brutal-sm space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-ink">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-none bg-ink text-white flex items-center justify-center shadow-brutal">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-ink">Demo Parcel Lookup &amp; Twin Extrusion</h3>
                  <p className="text-xs text-ink-soft">
                    Look up an identifier from this deployment&apos;s synthetic catalogue and extrude its massing model.
                    No national parcel dataset is loaded and no setback or building-code rule is applied.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-accent-strong bg-accent-faint border-2 border-ink px-2 py-1 rounded-none">
                  POST /ids/national-ulpin/verify-parcel
                </span>
              </div>
            </div>

            {/* Presets */}
            <div>
              <div className="text-[11px] font-bold text-ink-soft mb-1.5">Sample National ULPINs from DB:</div>
              <div className="flex flex-wrap gap-2">
                {['EFI7V44HUACG2U', 'EFBN5NS0DOLXLD', 'EFDDADJ2UGBN6Y', 'EFG49POQQEF0OH', 'FF3JXZ6BPAFXZ6', DEMO_ULPIN].map((u) => (
                  <button
                    key={u}
                    onClick={() => {
                      setNationalUlpinInput(u);
                      handleVerifyStoredParcel(u);
                    }}
                    className={`px-2.5 py-1 text-xs font-mono rounded-none border-2 transition ${
                      nationalUlpinInput === u
                        ? 'bg-ink text-white border-ink font-bold'
                        : 'bg-canvas text-ink hover:bg-canvas border-ink'
                    }`}
                  >
                    {u} {u === DEMO_ULPIN ? '(Airoli Hero)' : ''}
                  </button>
                ))}
              </div>
            </div>

            {/* Input & Action */}
            <div className="flex flex-col sm:flex-row items-center gap-2">
              <input
                type="text"
                value={nationalUlpinInput}
                onChange={(e) => setNationalUlpinInput(e.target.value.toUpperCase())}
                placeholder="Enter 14-char national ULPIN (e.g. EFI7V44HUACG2U)"
                className="w-full sm:flex-1 px-3.5 py-2.5 rounded-none border-2 border-ink font-mono text-sm uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
              <Button
                variant="primary"
                onClick={() => handleVerifyStoredParcel()}
                disabled={verifyingParcel || !nationalUlpinInput.trim()}
                className="w-full sm:w-auto shrink-0 flex items-center gap-2"
              >
                {verifyingParcel ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                Verify Stored Parcel
              </Button>
              <Button
                variant="secondary"
                onClick={handleExtrudeNationalTwin}
                disabled={extrudingNational || !nationalUlpinInput.trim()}
                className="w-full sm:w-auto shrink-0 flex items-center gap-2"
              >
                {extrudingNational ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 text-accent-strong" />}
                Extrude 3D Twin
              </Button>
            </div>

            {/* Verified Parcel Result Card */}
            {verifiedParcel && (
              <div className="p-4 rounded-none bg-chalk text-ink border-2 border-ink animate-rise-in text-xs space-y-3 font-mono">
                <div className="flex items-center justify-between border-b border-slate-700 pb-2">
                  <span className="flex items-center gap-2 text-emerald-400 font-bold">
                    <CheckCircle2 className="w-4 h-4" />
                    {verifiedParcel.message}
                  </span>
                  <Badge tone={verifiedParcel.valid ? 'green' : 'red'}>
                    {verifiedParcel.valid ? 'CHECKSUM MATCHES' : 'INVALID'}
                  </Badge>
                </div>
                <p className="text-[10px] leading-relaxed text-ink-soft">
                  Checksum self-consistency only: this confirms the identifier encodes the same
                  geometry the caller supplied. It is not an authenticity check against any
                  government register, and it says nothing about ownership, title or approval.
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <div className="text-ink-soft text-[10px]">ULPIN</div>
                    <div className="text-sm font-bold text-white select-all">{verifiedParcel.ulpin}</div>
                  </div>
                  <div>
                    <div className="text-ink-soft text-[10px]">Survey / CTS Number</div>
                    <div className="text-sm font-bold text-ink-mut">{verifiedParcel.survey_number || 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-ink-soft text-[10px]">Centroid Coordinates</div>
                    <div className="text-xs text-ink-mut">{verifiedParcel.centroid_lat?.toFixed(5)}, {verifiedParcel.centroid_lng?.toFixed(5)}</div>
                  </div>
                  <div>
                    <div className="text-ink-soft text-[10px]">Cadastral Area</div>
                    <div className="text-xs text-ink-mut">{verifiedParcel.area_m2 ? `${Math.round(verifiedParcel.area_m2).toLocaleString()} m²` : 'N/A'}</div>
                  </div>
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-slate-700">
                  <span className="text-[11px] text-ink-soft">Generated dataset tag: {verifiedParcel.boundary_code} · Class: {verifiedParcel.zonal_class || 'RESIDENTIAL'} (modelled, not a statutory zoning determination)</span>
                  <a
                    href={PROPERTY_CARD_PDF_URL(verifiedParcel.ulpin)}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-1 bg-ink hover:bg-ink text-white rounded-none font-bold text-xs flex items-center gap-1 transition"
                  >
                    <Download className="w-3 h-3" /> Property Card (PDF)
                  </a>
                </div>
              </div>
            )}

            {/* National Twin Extrusion Result */}
            {nationalTwinResult && (
              <div className="p-4 rounded-none bg-emerald-50 border-2 border-ink text-xs text-emerald-950 space-y-2 animate-rise-in font-mono">
                <div className="flex items-center justify-between">
                  <span className="font-bold flex items-center gap-1.5 text-emerald-900">
                    <Sparkles className="w-4 h-4 text-emerald-600" />
                    3D Digital Twin Extruded Successfully
                  </span>
                  <span className="text-[10px] text-emerald-700 font-bold">NBC 2016 Setback</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-[11px]">
                  {/* No defaults. `|| 15`, `|| 5` and `|| 1.8` reported a
                      15 m, five-storey, 1.8 FSI building for every parcel that
                      the engine had not actually measured. */}
                  <div>Structure Code: <strong>{nationalTwinResult.building_code || nationalTwinResult.twin?.building_code || '--'}</strong></div>
                  <div>Height: <strong>{nationalTwinResult.height_m ?? nationalTwinResult.twin?.height_m ?? '--'}{nationalTwinResult.height_m ?? nationalTwinResult.twin?.height_m != null ? 'm' : ''}</strong></div>
                  <div>Floors: <strong>{nationalTwinResult.floors ?? nationalTwinResult.twin?.floors ?? '--'}{nationalTwinResult.floors ?? nationalTwinResult.twin?.floors != null ? 'F' : ''}</strong></div>
                  <div>FSI: <strong>{nationalTwinResult.fsi ?? nationalTwinResult.twin?.fsi ?? '--'}</strong></div>
                </div>
              </div>
            )}
          </Card>

          {/* Section B: Interactive Polygon Ring Derivation & Verification */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <Card className="p-5 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-ink">
                <div className="flex items-center gap-2">
                  <Compass className="w-4 h-4 text-accent-strong" />
                  <h4 className="font-bold text-sm text-ink font-display">Interactive WGS-84 Polygon Ring Derivation</h4>
                </div>
                <span className="text-[10px] font-mono text-ink-mut">POST /ids/national-ulpin/derive</span>
              </div>
              <p className="text-xs text-ink-soft">
                Enter polygon ring vertices in <code className="font-mono text-accent-strong">[lat, lon]</code> format to deterministically derive a 14-character identifier. This is a locally implemented
                scheme for demo data, not an official or published specification:
              </p>

              {/* City ring presets */}
              <div className="flex flex-wrap gap-1.5 text-[11px]">
                <span className="text-ink-mut">Presets:</span>
                {[
                  { name: 'Airoli Pilot', ring: [[19.1550, 72.9980], [19.1565, 72.9980], [19.1565, 72.9995], [19.1550, 72.9995], [19.1550, 72.9980]] },
                  { name: 'Mumbai BKC', ring: [[19.0657, 72.8680], [19.0670, 72.8680], [19.0670, 72.8695], [19.0657, 72.8695], [19.0657, 72.8680]] },
                  { name: 'Pune IT Park', ring: [[18.5912, 73.7380], [18.5925, 73.7380], [18.5925, 73.7395], [18.5912, 73.7395], [18.5912, 73.7380]] },
                  { name: 'Bengaluru EC', ring: [[12.8452, 77.6601], [12.8465, 77.6601], [12.8465, 77.6616], [12.8452, 77.6616], [12.8452, 77.6601]] },
                  { name: 'Delhi CP', ring: [[28.6315, 77.2167], [28.6328, 77.2167], [28.6328, 77.2182], [28.6315, 77.2182], [28.6315, 77.2167]] },
                ].map((p) => (
                  <button
                    key={p.name}
                    onClick={() => setRingInput(JSON.stringify(p.ring, null, 2))}
                    className="px-2 py-0.5 rounded-none bg-canvas border-2 border-ink text-ink hover:text-ink hover:bg-canvas"
                  >
                    {p.name}
                  </button>
                ))}
              </div>

              <textarea
                value={ringInput}
                onChange={(e) => setRingInput(e.target.value)}
                rows={6}
                className="w-full font-mono text-xs p-3 rounded-none border-2 border-ink focus:outline-none focus:ring-2 focus:ring-accent/40 bg-canvas text-ink"
              />

              <div className="flex items-center gap-2 pt-1">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleDeriveRing}
                  disabled={deriving}
                  className="flex items-center gap-1.5"
                >
                  {deriving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Calculator className="w-3.5 h-3.5" />}
                  Derive 14-Digit ULPIN
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleVerifyRing}
                  disabled={deriving}
                  className="flex items-center gap-1.5"
                >
                  Verify against Target
                </Button>
              </div>
            </Card>

            {/* Derivation Output Card */}
            <Card className="p-5 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-ink">
                <div className="flex items-center gap-2">
                  <QrCode className="w-4 h-4 text-emerald-600" />
                  <h4 className="font-bold text-sm text-ink font-display">Identifier Derivation Output</h4>
                </div>
                {derivedResult && (
                  <Badge tone={derivedResult.valid !== false ? 'green' : 'amber'}>
                    {derivedResult.valid !== false ? 'DETERMINISTIC' : 'VERIFIED'}
                  </Badge>
                )}
              </div>

              {derivedResult ? (
                <div className="space-y-3 font-mono text-xs">
                  <div className="p-3 rounded-none bg-canvas border-2 border-ink">
                    <div className="text-[10px] text-ink-mut uppercase font-bold">Derived Official 14-Character ULPIN</div>
                    <div className="text-xl font-black text-accent-strong select-all tracking-widest mt-0.5">
                      {derivedResult.ulpin}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div className="p-2.5 rounded-none bg-canvas border-2 border-ink">
                      <span className="text-ink-mut block">Method</span>
                      <span className="font-bold text-ink">{derivedResult.derivation?.method || 'radix36-sha256'}</span>
                    </div>
                    <div className="p-2.5 rounded-none bg-canvas border-2 border-ink">
                      <span className="text-ink-mut block">Cell Key</span>
                      <span className="font-bold text-ink">{derivedResult.derivation?.cell_key || 'N/A'}</span>
                    </div>
                    <div className="p-2.5 rounded-none bg-canvas border-2 border-ink">
                      <span className="text-ink-mut block">Centroid</span>
                      <span className="font-bold text-ink truncate">
                        {derivedResult.derivation?.centroid_latlon?.map((c: number) => c.toFixed(4)).join(', ') || 'Computed'}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-none bg-canvas border-2 border-ink">
                      <span className="text-ink-mut block">Vertices Analyzed</span>
                      <span className="font-bold text-ink">{derivedResult.derivation?.vertex_count || 4} points</span>
                    </div>
                  </div>

                  {derivedResult.derivation?.compliance_note && (
                    <p className="text-[10px] text-ink-soft leading-relaxed">
                      {derivedResult.derivation.compliance_note}
                    </p>
                  )}
                </div>
              ) : (
                <div className="h-48 flex flex-col items-center justify-center text-center p-4 border-2 border-dashed border-ink rounded-none text-ink-soft">
                  <Calculator className="w-8 h-8 text-ink-mut mb-2" />
                  <p className="text-xs">Click "Derive 14-Digit ULPIN" to run the demo identifier derivation.</p>
                </div>
              )}
            </Card>
          </div>

          {/* Section C: Batch Boundary Twin Extruder */}
          <Card className="p-5 border-ink">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-ink">
              <div className="flex items-center gap-2.5">
                <Layers className="w-5 h-5 text-accent-strong" />
                <div>
                  <h4 className="font-bold text-sm text-ink font-display">Batch Administrative Boundary 3D Twin Extruder</h4>
                  <p className="text-xs text-ink-soft">Mass-extrude all national parcels inside any state, district, or taluka boundary.</p>
                </div>
              </div>
              <span className="text-[10px] font-mono text-accent-strong bg-accent-faint border-2 border-ink px-2 py-1 rounded-none">
                POST /ids/national-twin/extrude-boundary
              </span>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-2 mt-3">
              <input
                type="text"
                value={boundaryCodeInput}
                onChange={(e) => setBoundaryCodeInput(e.target.value.toUpperCase())}
                placeholder="Boundary Code (e.g. MH-THANE-T-01-V-01)"
                className="w-full sm:flex-1 px-3.5 py-2 rounded-none border-2 border-ink font-mono text-xs uppercase"
              />
              <Button
                variant="primary"
                onClick={handleExtrudeBoundaryTwins}
                disabled={extrudingBoundary || !boundaryCodeInput.trim()}
                className="w-full sm:w-auto shrink-0 flex items-center gap-2 text-xs"
              >
                {extrudingBoundary ? <Loader2 className="w-4 h-4 animate-spin" /> : <Layers className="w-4 h-4" />}
                Extrude All Boundary Parcels
              </Button>
            </div>

            {boundaryExtrudeResult && (
              <div className="mt-3 p-3 rounded-none bg-chalk text-ink border-2 border-ink font-mono text-xs flex items-center justify-between">
                <span>Boundary: {boundaryCodeInput}</span>
                <span className="text-emerald-400 font-bold">
                  {boundaryExtrudeResult.message || 'Extrusion dispatched successfully'}
                </span>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* 2D Cadastre to 3D-ULPIN Extrusion Pipeline */}
      {activeTab === 'EXTRUSION' && (
      <Card className="p-6 bg-chalk from-white border-ink shadow-brutal-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-ink">
          <div className="flex items-center gap-3">
            {/* bg-chalk + text-white: a white icon on a white tile, invisible. The
                `from-accent` never painted because there is no gradient utility
                on the element. Accent is a fill, so it takes ink text. */}
              <div className="w-10 h-10 rounded-none bg-accent border-2 border-ink flex items-center justify-center text-ink shadow-brutal-sm">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-ink">AI 2D Cadastre → 3D-ULPIN Extrusion Pipeline</h2>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-none bg-accent-faint text-ink border-2 border-ink">
                  ISO 19152 LADM Part 3
                </span>
              </div>
              <p className="text-xs text-ink-soft mt-0.5">
                Automatically convert flat 2D land parcels into stratified 3D building twins with NBC setbacks, parking, units & air rights.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-none bg-canvas border-2 border-ink text-xs">
              <span className="text-ink-soft">2D Pending:</span>
              <span className="font-mono font-bold text-amber-600">{unextruded.length}</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-none bg-canvas border-2 border-ink text-xs">
              <span className="text-ink-soft">3D Twins:</span>
              <span className="font-mono font-bold text-emerald-700">{buildings.length}</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-none bg-canvas border-2 border-ink text-xs">
              <span className="text-ink-soft">Total Units:</span>
              <span className="font-mono font-bold text-accent-strong">{totalPrecinctUnits}</span>
            </div>
          </div>
        </div>

        {/* Action Bar */}
        <div className="mt-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <p className="text-xs text-ink max-w-xl">
            {unextruded.length > 0 ? (
              <>
                Detected <strong className="text-ink">{unextruded.length} flat 2D parcels</strong> in the cadastral registry that do not possess 3D-ULPIN units. Run the extrusion pipeline to mint deterministic 3D-ULPINs for all levels, units, and subterranean parking.
              </>
            ) : (
              <span className="text-emerald-700 font-bold flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" /> All 2D parcels in the generated Airoli Sector 8 dataset have modelled 3D twins and 3D-ULPINs
              </span>
            )}
          </p>

          {unextruded.length > 0 && (
            <Button
              onClick={handleExtrudeAll}
              disabled={extrudingAll}
              className="bg-accent hover:bg-accent/90 text-ink text-xs font-bold px-4 py-2.5 rounded-none shadow-brutal flex items-center gap-2 shrink-0"
            >
              {extrudingAll ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Extruding 2D Parcels & Minting 3D-IDs...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" /> Extrude All {unextruded.length} Parcels to 3D-ULPINs
                </>
              )}
            </Button>
          )}
        </div>

        {/* Extrusion Celebration Report */}
        {extrusionReport && (
          <div className="mt-4 p-4 rounded-none bg-emerald-50 border-2 border-ink text-xs animate-rise-in">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span className="font-bold text-emerald-950">{extrusionReport.message}</span>
              </div>
              <button
                onClick={() => setExtrusionReport(null)}
                className="text-[11px] text-emerald-700 hover:text-emerald-950 font-bold"
              >
                Dismiss
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3 pt-3 border-t border-emerald-200/60">
              {extrusionReport.buildings.slice(0, 3).map((b) => (
                <div key={b.code} className="p-2.5 rounded-none bg-white/80 border-2 border-emerald-200/50">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-ink font-mono text-[11px]">{b.code}</span>
                    <span className="text-[10px] text-emerald-700 font-bold">{unitCount(b)} Units</span>
                  </div>
                  <p className="text-[11px] text-ink-soft truncate mt-0.5">{b.name}</p>
                  <code className="block text-[10px] font-mono text-accent-strong truncate mt-1">
                    {b.building_3d_id}
                  </code>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Unextruded 2D Parcels Queue */}
        {unextruded.length > 0 && (
          <div className="mt-4 pt-4 border-t border-ink">
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-[11px] font-bold text-ink uppercase tracking-widest">
                Unextruded 2D Cadastre Parcels ({unextruded.length})
              </span>
              <span className="text-[11px] text-ink-mut">Click Extrude to mint on demand</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 max-h-56 overflow-y-auto pr-1">
              {unextruded.map((p) => (
                <div
                  key={p.ulpin}
                  className="p-3 rounded-none bg-canvas border-2 border-ink hover:border-ink transition flex items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs font-bold text-ink">{p.survey_number}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded-none bg-amber-100 text-amber-800 font-mono">
                        {p.suggested_typology}
                      </span>
                    </div>
                    <code className="text-[10px] font-mono text-ink-soft block truncate mt-0.5">{p.ulpin}</code>
                    <p className="text-[10px] text-ink-mut mt-0.5">
                      Area: {p.plot_area_m2}m² · Rec: {p.suggested_building_code} ({p.suggested_floors}F)
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleExtrudeSingle(p.ulpin)}
                    disabled={extrudingSingle === p.ulpin || extrudingAll}
                    className="text-[11px] shrink-0 font-bold text-accent-strong border-2 border-ink hover:bg-accent-faint"
                  >
                    {extrudingSingle === p.ulpin ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Extrude'}
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
      )}

      {/* Excel / CSV 3D ULPIN Studio Card */}
      {activeTab === 'SPREADSHEET' && (
      <Card className="p-6 bg-chalk from-white border-ink shadow-brutal-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-ink">
          <div className="flex items-center gap-3">
            {/* Same white-on-white tile as above. */}
              <div className="w-10 h-10 rounded-none bg-accent border-2 border-ink flex items-center justify-center text-ink shadow-brutal-sm">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-ink">Excel / CSV 3D ULPIN Studio & Bulk Extruder</h2>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-none bg-accent-faint text-ink border-2 border-ink">
                  Bulk Cadastral Ingestion
                </span>
              </div>
              <p className="text-xs text-ink-soft mt-0.5">
                Generate 3D digital twins, compute FSI & volumes, and mint ISO/IEC 7064 3D-ULPINs directly from spreadsheets.
              </p>
            </div>
          </div>

          {/* Download Sample Templates */}
          <div className="flex items-center gap-2 flex-wrap">
            <a
              href={EXCEL_TEMPLATE_URL}
              download="Bhu_Drishti_3D_ULPIN_Template.xlsx"
              className="px-3 py-1.5 rounded-none bg-white border-2 border-ink hover:border-ink text-ink hover:text-accent-strong text-xs font-bold transition flex items-center gap-1.5 shadow-brutal-sm"
            >
              <Download className="w-3.5 h-3.5 text-emerald-600" />
              Excel Template (.xlsx)
            </a>
            <a
              href={CSV_TEMPLATE_URL}
              download="Bhu_Drishti_3D_ULPIN_Template.csv"
              className="px-3 py-1.5 rounded-none bg-white border-2 border-ink hover:border-ink text-ink hover:text-accent-strong text-xs font-bold transition flex items-center gap-1.5 shadow-brutal-sm"
            >
              <Download className="w-3.5 h-3.5 text-accent-strong" />
              CSV Template (.csv)
            </a>
          </div>
        </div>

        {/* Upload & Execution Section */}
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
          <div className="md:col-span-2">
            <label className="block text-xs font-bold text-ink mb-1.5">
              Select or Drop Spreadsheet (.xlsx, .xls, .csv)
            </label>
            <div className="flex items-center gap-3">
              <input
                type="file"
                accept=".xlsx,.xls,.csv"
                onChange={handleSpreadsheetFileChange}
                className="block w-full text-xs text-ink-soft file:mr-3 file:py-2 file:px-4 file:rounded-none file:border-0 file:text-xs file:font-bold file:bg-accent-faint file:text-accent-strong hover:file:bg-accent-faint border-2 border-ink rounded-none p-1 bg-white"
              />
              <Button
                variant="primary"
                onClick={handleProcessSpreadsheet}
                disabled={!spreadsheetFile || processingSpreadsheet}
                className="shrink-0 bg-ink hover:bg-ink text-white font-bold text-xs"
              >
                {processingSpreadsheet ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-1.5" />
                    Extruding 3D Twins...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4 mr-1.5" />
                    Generate 3D ULPINs
                  </>
                )}
              </Button>
            </div>
            {spreadsheetFile && (
              <p className="text-[11px] text-accent-strong font-mono mt-1">
                Selected: {spreadsheetFile.name} ({(spreadsheetFile.size / 1024).toFixed(1)} KB)
              </p>
            )}
          </div>

          <div className="bg-accent-faint p-3.5 rounded-none border-2 border-ink text-xs text-ink space-y-1">
            <div className="font-bold flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-accent-strong" />
              Spreadsheet Ingestion Rules:
            </div>
            <ul className="text-[11px] text-ink list-disc list-inside space-y-0.5">
              <li>Auto-computes height, volumes & floor levels</li>
              <li>Calculates FSI against UDCPR 2020 limit (2.0)</li>
              <li>Mints 3D-ULPINs with Luhn Mod 36 checksums</li>
              <li>Stages records into Blockchain mempool</li>
            </ul>
          </div>
        </div>

        {/* Extrusion Results Display */}
        {spreadsheetResult && (
          <div className="mt-5 pt-4 border-t border-ink space-y-4 animate-rise-in">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-none bg-emerald-500 animate-ping" />
                <h3 className="font-bold text-sm text-ink">
                  Generated {spreadsheetResult.total_buildings_generated} 3D Buildings & {spreadsheetResult.total_3d_ulpins_minted} Stratified 3D-ULPINs
                </h3>
              </div>
              <span className="text-[10px] font-mono font-bold px-2.5 py-1 rounded-none bg-emerald-100 text-emerald-800 border-2 border-ink">
                {spreadsheetResult.blockchain_mempool_status}
              </span>
            </div>

            {/* Extruded Buildings Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {spreadsheetResult.buildings.map((bldg) => (
                <div key={bldg.building_code} className="bg-white rounded-none p-4 border-2 border-ink shadow-brutal-sm space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-sm text-ink">{bldg.building_name}</span>
                        <span className="px-2 py-0.5 rounded-none text-[10px] font-bold font-mono bg-accent-faint text-ink">
                          {bldg.building_code}
                        </span>
                      </div>
                      <code className="text-xs font-mono text-accent-strong block mt-0.5">
                        Base ULPIN: {bldg.parent_ulpin}
                      </code>
                    </div>
                    <span className={`px-2 py-0.5 rounded-none text-[10px] font-bold ${
                      bldg.fsi_status === 'PASS' ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                    }`}>
                      FSI: {bldg.calculated_fsi} ({bldg.fsi_status})
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-[10px] font-mono bg-canvas p-2.5 rounded-none border-2 border-ink">
                    <div>
                      <span className="text-ink-soft block font-sans">Floors:</span>
                      <span className="font-bold text-ink">{bldg.total_floors} ({bldg.total_height_m}m)</span>
                    </div>
                    <div>
                      <span className="text-ink-soft block font-sans">Footprint:</span>
                      <span className="font-bold text-ink">{bldg.footprint_area_m2}m²</span>
                    </div>
                    <div>
                      <span className="text-ink-soft block font-sans">Built-Up:</span>
                      <span className="font-bold text-ink">{bldg.total_built_up_area_m2}m²</span>
                    </div>
                  </div>

                  {/* Units Table */}
                  <div className="max-h-48 overflow-y-auto rounded-none border-2 border-ink text-[11px]">
                    <table className="w-full text-left">
                      <thead className="bg-canvas text-ink-soft font-bold text-[10px]">
                        <tr>
                          <th className="p-2">Unit</th>
                          <th className="p-2">Level</th>
                          <th className="p-2">Owner</th>
                          <th className="p-2">3D-ULPIN</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 font-mono text-[10px]">
                        {bldg.units.map((u) => (
                          <tr key={u.proposed_3d_id} className="hover:bg-canvas">
                            <td className="p-2 font-bold text-ink">{u.unit_number}</td>
                            <td className="p-2 text-ink-soft">{u.level_code}</td>
                            <td className="p-2 font-sans truncate max-w-[100px] text-ink">{u.owner_name}</td>
                            <td className="p-2 text-accent-strong flex items-center justify-between gap-1">
                              <span className="truncate max-w-[150px]">{u.proposed_3d_id}</span>
                              <button
                                onClick={() => {
                                  navigator.clipboard.writeText(u.proposed_3d_id);
                                  showToast(`Copied ${u.proposed_3d_id}`);
                                }}
                                className="text-ink-soft hover:text-accent-strong p-0.5"
                                title="Copy 3D-ULPIN"
                              >
                                <Copy className="w-3 h-3" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
      )}

      {/* Main decoder and generator row */}
      {activeTab === 'DECODER' && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Decoder */}
        <Card className="p-5">
          <div className="flex items-center gap-2 text-sm font-bold text-ink mb-4">
            <QrCode className="w-4 h-4 text-accent-strong" /> Decode & verify 3D-ULPIN
          </div>
          <Field
            label="3D-ID string"
            value={inputID}
            onChange={(e) => setInputID(e.target.value)}
            hint="Checksum validated with ISO/IEC 7064 Luhn Mod 36"
          />
          <div className="flex flex-wrap gap-2 mt-2 mb-4">
            {examples.map((ex) => (
              <button key={ex} onClick={() => { setInputID(ex); handleDecode(ex); }} className="font-mono text-[10px] bg-canvas hover:bg-canvas text-ink px-2 py-1 rounded-none transition border-2 border-ink">
                {ex}
              </button>
            ))}
          </div>
          <Button onClick={() => handleDecode()} disabled={decoding}>
            <Calculator className="w-3.5 h-3.5" /> {decoding ? 'Verifying…' : 'Decode & Validate'}
          </Button>

          {decodeError && <p className="mt-3 text-xs font-bold text-crimson-600">{decodeError}</p>}

          {decoded && (
            <div className="mt-4 space-y-2 animate-rise-in">
              <div className="flex items-center justify-between text-xs">
                <span className="text-ink-soft">ID</span>
                <div className="flex items-center gap-1.5 min-w-0">
                  <code className="font-mono text-[11px] font-bold text-ink break-all text-right">{decoded.raw_input}</code>
                  <button onClick={() => copy(decoded.raw_input)} className="text-ink-mut hover:text-accent-strong shrink-0"><Copy className="w-3.5 h-3.5" /></button>
                </div>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-ink-soft">Validity</span>
                <Badge tone={decoded.is_valid ? 'green' : 'red'}>{decoded.is_valid ? 'Valid Checksum' : 'Invalid'}</Badge>
              </div>
              {decoded.validation_message && (
                <p className={`text-[11px] font-bold ${decoded.is_valid ? 'text-emerald-700' : 'text-crimson-600'}`}>{decoded.validation_message}</p>
              )}
              {decoded.parsed_components && (
                <div className="border-t border-ink pt-2 space-y-1.5">
                  {[
                    ['Parent ULPIN', decoded.parsed_components.parent_14_char_ulpin],
                    ['Type', `${decoded.parsed_components.type_code} · ${decoded.parsed_components.type_description}`],
                    ['Building', decoded.parsed_components.building_code],
                    ['Level', decoded.parsed_components.level_code],
                    ['Unit', decoded.parsed_components.unit_code],
                    ['Check digit', decoded.parsed_components.checksum_character],
                  ].map(([k, v]) => (
                    <div key={String(k)} className="flex items-center justify-between gap-3 text-xs">
                      <span className="text-ink-soft capitalize">{String(k)}</span>
                      <code className="font-mono text-[11px] font-bold text-ink text-right">{String(v)}</code>
                    </div>
                  ))}
                </div>
              )}
              {decoded.checksum_verification && (
                <div className="flex items-center justify-between text-xs bg-emerald-50/60 border-2 border-emerald-100 rounded-none px-2.5 py-2">
                  <span className="text-ink-soft">{decoded.checksum_verification.algorithm}</span>
                  <Badge tone={decoded.checksum_verification.matches ? 'green' : 'red'}>
                    {decoded.checksum_verification.computed_check_digit} ≈ {decoded.checksum_verification.received_check_digit}
                  </Badge>
                </div>
              )}
            </div>
          )}
        </Card>

        {/* Generator */}
        <Card className="p-5">
          <div className="flex items-center gap-2 text-sm font-bold text-ink mb-4">
            <Dices className="w-4 h-4 text-emerald-600" /> Generate compliant 3D-ID
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Parent ULPIN" value={gen.parent_ulpin} onChange={(e) => setGen({ ...gen, parent_ulpin: e.target.value })} />
            <Field label="Type code (U/C/P/A)" value={gen.type_code} onChange={(e) => setGen({ ...gen, type_code: e.target.value })} />
            <Field label="Building code" value={gen.building_code} onChange={(e) => setGen({ ...gen, building_code: e.target.value })} />
            <Field label="Level code (e.g. L01, B1)" value={gen.level_code} onChange={(e) => setGen({ ...gen, level_code: e.target.value })} />
            <Field label="Unit code" className="col-span-2" value={gen.unit_code} onChange={(e) => setGen({ ...gen, unit_code: e.target.value })} />
          </div>
          <div className="mt-3">
            <Button variant="success" onClick={handleGenerate} disabled={generating}>
              <Dices className="w-3.5 h-3.5" /> {generating ? 'Generating…' : 'Generate 3D-ULPIN'}
            </Button>
          </div>

          {generated && (
            <div className="mt-4 bg-emerald-50 border-2 border-ink rounded-none p-3.5 animate-rise-in">
              <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-800">
                <CheckCircle2 className="w-4 h-4" /> Generated — checksummed & collision-free
              </div>
              <div className="mt-2 flex items-center justify-between gap-2">
                <code className="font-mono text-sm font-black text-emerald-900 break-all">{generated.proposed_3d_id}</code>
                <button onClick={() => copy(generated.proposed_3d_id)} className="text-emerald-600 hover:text-emerald-800 shrink-0"><Copy className="w-4 h-4" /></button>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Badge tone="green" dot>ISO/IEC 7064</Badge>
                {generated.specification && <Badge tone="slate">{generated.specification}</Badge>}
              </div>
              {generated.disclaimer && <p className="mt-2 text-[10px] text-emerald-700/70 leading-relaxed">{generated.disclaimer}</p>}
            </div>
          )}
        </Card>
      </div>
      )}

      {/* ----------------- PRECINCT 3D-ULPIN REGISTRY EXPLORER ----------------- */}
      {activeTab === 'PRECINCT' && (
      <Card className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink pb-4">
          <div>
            <div className="flex items-center gap-2">
              <Building2 className="w-5 h-5 text-accent-strong" />
              <h2 className="text-lg font-black text-ink font-display">Precinct 3D-ULPIN Registry Explorer</h2>
              <span className="text-xs px-2 py-0.5 rounded-none font-mono font-bold bg-accent-faint text-accent-strong">
                {totalPrecinctUnits} Total 3D ULPINs
              </span>
            </div>
            <p className="text-xs text-ink-soft mt-0.5">
              Select any building from the Airoli Sector 8 precinct to inspect and verify all its constituent vertical unit 3D-IDs.
            </p>
          </div>

          {selectedBuilding && (
            <button
              onClick={copyAllForBuilding}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold text-accent-strong bg-accent-faint hover:bg-accent/20 transition border-2 border-ink"
            >
              <Copy className="w-3.5 h-3.5" /> Export All for {selectedBuilding.code} (CSV)
            </button>
          )}
        </div>

        {/* Building Selector Pills */}
        <div className="mt-4 flex flex-wrap gap-1.5">
          {buildings.map((b) => {
            const isSel = b.code === selectedCode;
            const isFlagged =
              b.status === 'DEMO_ELEVATED_FSI' || b.status === 'DEMO_EPOCH_COMPARISON';
            return (
              <button
                key={b.code}
                onClick={() => {
                  setSelectedCode(b.code);
                  setUnitSearch('');
                }}
                className={`px-3 py-1.5 rounded-none text-xs font-bold transition flex items-center gap-1.5 border-2 ${
                  isSel
                    ? 'bg-accent text-white border-ink shadow-brutal-sm'
                    : isFlagged
                    ? 'bg-red-50 text-red-700 border-ink hover:bg-red-100'
                    : 'bg-canvas text-ink-soft border-ink hover:text-ink hover:border-ink'
                }`}
              >
                <span>{b.code}</span>
                <span className={`text-[10px] px-1.5 py-0.2 rounded-none border-2 border-ink font-mono font-black ${isSel ? 'bg-ink text-white' : 'bg-canvas text-ink-mut'}`}>
                  {unitCount(b)}
                </span>
              </button>
            );
          })}
        </div>

        {/* Selected Building Overview Strip */}
        {selectedBuilding && (
          <div className="mt-4 p-4 rounded-none bg-canvas border-2 border-ink flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="w-10 h-10 rounded-none bg-accent-faint border-2 border-ink flex items-center justify-center font-bold text-accent-strong">
                {selectedBuilding.code}
              </span>
              <div>
                <h3 className="font-bold text-ink text-sm flex items-center gap-2">
                  {selectedBuilding.name}
                  <StatusBadge status={selectedBuilding.status || 'UNSPECIFIED'} />
                </h3>
                <div className="flex items-center gap-3 text-xs text-ink-soft mt-0.5 font-mono">
                  <span>Parent ULPIN: <strong className="text-ink">{selectedBuilding.parent_ulpin}</strong></span>
                  <span>·</span>
                  <span>{selectedBuilding.floors} Floors</span>
                  <span>·</span>
                  <span>{selectedBuilding.height_m} m</span>
                  <span>·</span>
                  <span>{unitCount(selectedBuilding)} Units</span>
                </div>
              </div>
            </div>

            {selectedBuilding.building_3d_id && (
              <div className="flex items-center gap-2 bg-chalk px-3 py-2 rounded-none border-2 border-ink">
                <div className="text-right">
                  <div className="text-[10px] uppercase font-bold text-ink-mut">Master Building 3D-ULPIN</div>
                  <code className="text-xs font-mono font-bold text-accent-strong">{selectedBuilding.building_3d_id}</code>
                </div>
                <button
                  onClick={() => copy(selectedBuilding.building_3d_id!)}
                  className="p-1.5 text-ink-mut hover:text-accent-strong rounded-none hover:bg-canvas transition"
                  title="Copy Master 3D-ULPIN"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        )}

        {/* Units Filter Row */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-ink-mut" />
            <input
              type="text"
              placeholder="Search units (e.g. 101, L02, G01)..."
              value={unitSearch}
              onChange={(e) => setUnitSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-canvas border-2 border-ink rounded-none text-ink placeholder:text-ink-mut outline-none focus:border-ink"
            />
          </div>

          <div className="flex items-center gap-1 bg-canvas border-2 border-ink rounded-none p-0.5 text-xs">
            {(
              [
                ['ALL', 'All Units'],
                ['U', 'Residential (U)'],
                ['C', 'Commercial (C)'],
                ['P', 'Parking (P)'],
                ['A', 'Air Rights (A)'],
              ] as const
            ).map(([t, label]) => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`px-2.5 py-1 rounded-none text-[11px] font-bold transition ${
                  typeFilter === t ? 'bg-accent text-white shadow-xs' : 'text-ink-soft hover:text-ink'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Units Table */}
        <div className="mt-3 border-2 border-ink rounded-none overflow-hidden">
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-canvas/90 sticky top-0 border-b border-ink text-[11px] font-bold text-ink-soft backdrop-blur-xs">
                <tr>
                  <th className="py-2.5 px-3">Unit</th>
                  <th className="py-2.5 px-3">Level</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Elevation Span</th>
                  <th className="py-2.5 px-3">Built-up</th>
                  <th className="py-2.5 px-3">Proposed 3D-ULPIN</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink/5">
                {filteredUnits.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-ink-soft text-xs">
                      No constituent units found matching criteria.
                    </td>
                  </tr>
                ) : (
                  filteredUnits.map((u) => {
                    const isCopied = copiedId === u.proposed_3d_id;
                    const typeBadge =
                      u.unit_type === 'P'
                        ? { tone: 'slate' as const, label: 'Parking' }
                        : u.unit_type === 'A'
                        ? { tone: 'sky' as const, label: 'Air Right' }
                        : u.unit_type === 'C'
                        ? { tone: 'amber' as const, label: 'Commercial' }
                        : { tone: 'green' as const, label: 'Residential' };

                    return (
                      <tr key={u.unit_number + u.proposed_3d_id} className="hover:bg-canvas transition">
                        <td className="py-2.5 px-3 font-bold text-ink">
                          {u.unit_number}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-ink">
                          {u.level_code}
                        </td>
                        <td className="py-2.5 px-3">
                          <Badge tone={typeBadge.tone}>{typeBadge.label}</Badge>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px] text-ink-soft">
                          {u.min_z.toFixed(1)} – {u.max_z.toFixed(1)} m
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px] text-ink">
                          {u.built_up_area_m2} m²
                        </td>
                        <td className="py-2.5 px-3">
                          <code className="font-mono text-[11px] font-bold text-accent-strong bg-accent-faint px-2 py-0.5 rounded-none border-2 border-accent/15 select-all">
                            {u.proposed_3d_id}
                          </code>
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => copy(u.proposed_3d_id)}
                              className={`p-1.5 rounded-none border-2 transition ${
                                isCopied
                                  ? 'bg-emerald-50 text-emerald-600 border-ink'
                                  : 'text-ink-mut hover:text-ink border-ink hover:bg-canvas'
                              }`}
                              title="Copy 3D-ULPIN"
                            >
                              {isCopied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                            </button>
                            <button
                              onClick={() => verifyInEngine(u.proposed_3d_id)}
                              className="px-2 py-1 rounded-none text-[10px] font-bold text-accent-strong bg-accent-faint hover:bg-accent/20 transition border-2 border-ink inline-flex items-center gap-1"
                              title="Load and verify in 3D-ID engine above"
                            >
                              <ShieldCheck className="w-3 h-3" /> Verify
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </Card>
      )}

      {/* Identifier scheme reference modal */}
      {specModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-rise-in">
          <div className="bg-white rounded-none max-w-2xl w-full border-2 border-ink shadow-brutal-xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="p-4 border-b border-ink flex items-center justify-between bg-canvas">
              <div className="flex items-center gap-2">
                <Globe2 className="w-4 h-4 text-accent-strong" />
                <h3 className="font-bold text-sm text-ink font-display">Identifier Scheme Reference (demo, not a published specification)</h3>
              </div>
              <button
                onClick={() => setSpecModalOpen(false)}
                className="p-1 text-ink-soft hover:text-ink rounded-none"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 font-mono text-xs text-ink bg-slate-900 text-ink-mut">
              <pre className="whitespace-pre-wrap">{JSON.stringify(nationalSpec, null, 2)}</pre>
            </div>

            <div className="p-3 border-t border-ink flex items-center justify-between bg-canvas text-xs">
              <span className="text-[11px] text-ink-soft">Locally written demo specification &mdash; not published by or issued under any government department</span>
              <Button variant="secondary" size="sm" onClick={() => setSpecModalOpen(false)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        <DemoHint />
        <StatusBadge status="DETERMINISTIC" />
        <span className="text-[11px] text-ink-soft">
          All {catalogueTotals.total_3d_ids || totalPrecinctUnits} precinct 3D identifiers generated
          by this demo. Synthetic, not authority-issued.
        </span>
      </div>
    </div>
  );
};