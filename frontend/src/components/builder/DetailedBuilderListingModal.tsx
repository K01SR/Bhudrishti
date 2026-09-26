import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  X,
  Building2,
  ClipboardCheck,
  Sparkles,
  Loader2,
  Copy,
  Check,
  PenTool,
  MapPin,
} from 'lucide-react';
import {
  fileDetailedBuilderSubmission,
  DetailedBuilderSubmissionResponse,
  DetailedBuilderFloorLabel,
} from '../../services/api';
import { Button, Badge } from '../ui';
import { useApp } from '../../context/AppContext';

interface DetailedBuilderListingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  defaultUlpin?: string;
}

type Pt = [number, number];

const DEFAULT_FOOTPRINT: Pt[] = [
  [0, 0],
  [24, 0],
  [24, 12],
  [0, 12],
];

function buildFloorLabels(floors: number, basements: number): DetailedBuilderFloorLabel[] {
  const labels: DetailedBuilderFloorLabel[] = [];
  for (let b = 1; b <= basements; b += 1) {
    labels.push({ level_code: `B${b}`, name: `Basement ${b}`, use: 'Parking' });
  }
  // `floors` counts floors ABOVE ground, and the ground floor is one of them,
  // so there are `floors - 1` levels above G. Labelling floors+1 rows here
  // would persist a level that contradicts floors_above_ground.
  labels.push({ level_code: 'G', name: 'Ground', use: 'Commercial' });
  for (let i = 1; i < floors; i += 1) {
    labels.push({ level_code: `L${String(i).padStart(2, '0')}`, name: `Level ${i}`, use: 'Residential' });
  }
  return labels;
}

function shoelaceAreaM2(points: Pt[]): number {
  if (points.length < 3) return 0;
  let sum = 0;
  for (let i = 0; i < points.length; i += 1) {
    const [x1, y1] = points[i];
    const [x2, y2] = points[(i + 1) % points.length];
    sum += x1 * y2 - x2 * y1;
  }
  return Math.abs(sum) / 2;
}

const ED_W = 300;
const ED_H = 200;
const ED_M = 20;
const ED_SCALE = 10; // px per metre
const ED_MAX_X = (ED_W - 2 * ED_M) / ED_SCALE;
const ED_MAX_Y = (ED_H - 2 * ED_M) / ED_SCALE;
/** Snap to a 0.5 m grid and keep the point inside the drawable plot. */
const clampToGrid = (v: number, max: number): number =>
  Math.min(max, Math.max(0, Math.round(v * 2) / 2));
const toPx = ([x, y]: Pt): [number, number] => [
  ED_M + x * ED_SCALE,
  ED_M + (ED_H - 2 * ED_M - y * ED_SCALE),
];

interface FootprintEditorProps {
  points: Pt[];
  onChange: (pts: Pt[]) => void;
}

const FootprintEditor: React.FC<FootprintEditorProps> = ({ points, onChange }) => {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // The svg is laid out `w-full` against a fixed viewBox, so client pixels are
  // not viewBox units. Without this projection every click lands in the wrong
  // place on any screen wider than 300px.
  const projectEvent = (e: React.PointerEvent): Pt => {
    const rect = svgRef.current!.getBoundingClientRect();
    const vx = ((e.clientX - rect.left) / rect.width) * ED_W;
    const vy = ((e.clientY - rect.top) / rect.height) * ED_H;
    const sx = clampToGrid((vx - ED_M) / ED_SCALE, ED_MAX_X);
    const sy = clampToGrid((ED_H - 2 * ED_M - (vy - ED_M)) / ED_SCALE, ED_MAX_Y);
    return [sx, sy];
  };

  const addFromEvent = (e: React.PointerEvent) => {
    if (dragIndex !== null || !svgRef.current) return;
    if (points.length >= 16) return;
    onChange([...points, projectEvent(e)]);
  };

  return (
    <div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${ED_W} ${ED_H}`}
        className="w-full border-2 border-ink bg-canvas touch-none select-none"
        onPointerDown={addFromEvent}
        onPointerMove={(e) => {
          if (dragIndex === null || !svgRef.current) return;
          const next = [...points];
          next[dragIndex] = projectEvent(e);
          onChange(next);
        }}
        onPointerUp={() => setDragIndex(null)}
      >
        {Array.from({ length: Math.floor((ED_W - 2 * ED_M) / (ED_SCALE * 5)) + 1 }, (_, i) => i * 5).map((m) => (
          <line key={`v${m}`} x1={ED_M + m * ED_SCALE} y1={ED_M} x2={ED_M + m * ED_SCALE} y2={ED_H - ED_M} stroke="#000" strokeOpacity={0.12} />
        ))}
        {Array.from({ length: Math.floor((ED_H - 2 * ED_M) / (ED_SCALE * 5)) + 1 }, (_, i) => i * 5).map((m) => (
          <line key={`h${m}`} x1={ED_M} y1={ED_H - ED_M - m * ED_SCALE} x2={ED_W - ED_M} y2={ED_H - ED_M - m * ED_SCALE} stroke="#000" strokeOpacity={0.12} />
        ))}
        {[0, 5, 10, 15, 20, 25].map((m) => (
          <text key={`xv${m}`} x={ED_M + m * ED_SCALE} y={ED_H - 4} fontSize={7} fill="#666">
            {m}
          </text>
        ))}
        {[0, 5, 10, 15].map((m) => (
          <text key={`xh${m}`} x={2} y={ED_H - ED_M - m * ED_SCALE + 2} fontSize={7} fill="#666">
            {m}
          </text>
        ))}

        {points.length >= 3 && (
          <polygon points={points.map((p) => toPx(p).join(',')).join(' ')} fillOpacity={0.15} strokeWidth={2}
            style={{ fill: 'rgb(var(--accent) / 0.15)', stroke: 'rgb(var(--accent))' }} />
        )}
        {points.length === 2 && (
          <line x1={toPx(points[0])[0]} y1={toPx(points[0])[1]} x2={toPx(points[1])[0]} y2={toPx(points[1])[1]} strokeWidth={1.5} style={{ stroke: 'rgb(var(--accent))' }} />
        )}
        {points.map((p, i) => {
          const [cx, cy] = toPx(p);
          return (
            <g key={`${i}-${cx}-${cy}`}>
              <circle
                cx={cx}
                cy={cy}
                r={7}
                fill="transparent"
                onPointerDown={(e) => {
                  e.stopPropagation();
                  setDragIndex(i);
                }}
              />
              <circle cx={cx} cy={cy} r={3.5} style={{
                fill: dragIndex === i ? 'rgb(var(--accent))' : '#111',
                stroke: dragIndex === i ? 'rgb(var(--accent))' : '#111',
              }} />
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] font-mono text-ink">
        <Badge tone={points.length >= 3 ? 'green' : 'amber'}>
          {points.length} vertices · {shoelaceAreaM2(points).toFixed(1)} m²
        </Badge>
        <span className="text-ink-mut">click canvas to add a vertex · drag a dot to move it</span>
      </div>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={() => onChange(DEFAULT_FOOTPRINT)}
          className="px-2.5 py-1 text-[10px] font-bold text-ink bg-canvas border-2 border-ink rounded-none hover:bg-accent transition"
        >
          Reset 24×12 parcel rectangle
        </button>
        {points.length > 0 && (
          <button
            type="button"
            onClick={() => onChange(points.slice(0, -1))}
            className="px-2.5 py-1 text-[10px] font-bold text-ink bg-canvas border-2 border-ink rounded-none hover:bg-accent transition"
          >
            Remove last vertex
          </button>
        )}
        <button
          type="button"
          onClick={() => onChange([])}
          className="px-2.5 py-1 text-[10px] font-bold text-ink bg-canvas border-2 border-ink rounded-none hover:bg-accent transition"
        >
          Clear
        </button>
      </div>
    </div>
  );
};

export const DetailedBuilderListingModal: React.FC<DetailedBuilderListingModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  defaultUlpin = '20260925001301',
}) => {
  const { showToast } = useApp();
  const [activeTab, setActiveTab] = useState<'statutory' | 'massing' | 'utilities' | 'preview'>('statutory');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<DetailedBuilderSubmissionResponse | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Detailed form state
  const [projectName, setProjectName] = useState('Emerald Horizon Towers');
  const [parcelUlpin, setParcelUlpin] = useState(defaultUlpin);
  const [address, setAddress] = useState('');
  const [locality, setLocality] = useState('');
  const [footprint, setFootprint] = useState<Pt[]>(DEFAULT_FOOTPRINT);
  const [floorLabels, setFloorLabels] = useState<DetailedBuilderFloorLabel[]>(() => buildFloorLabels(8, 1));
  // Left empty on purpose. These were pre-filled with identifiers shaped like
  // real MahaRERA and municipal records, so a builder who opened the form and
  // submitted it was publishing those numbers against a body that never
  // issued them. Nothing here is checked against a registry, so the fields
  // record a claim and are labelled as one.
  const [reraId, setReraId] = useState('');
  const [sanctionNo, setSanctionNo] = useState('');
  const [ccDate, setCcDate] = useState('');

  const [typology, setTypology] = useState('tower');
  const [floors, setFloors] = useState(8);
  const [basements, setBasements] = useState(1);
  const [floorHeight, setFloorHeight] = useState(3.5);
  const [fsi] = useState(1.85);

  const [setbackFront, setSetbackFront] = useState(6.5);
  const [setbackRear, setSetbackRear] = useState(5.0);
  const [setbackNorth, setSetbackNorth] = useState(4.5);
  const [setbackSouth, setSetbackSouth] = useState(4.5);

  const [subsurfaceDepth, setSubsurfaceDepth] = useState(3.5);
  const [sewerDepth, setSewerDepth] = useState(2.2);
  const [stormwaterTank, setStormwaterTank] = useState(120);
  const [solarCapacity, setSolarCapacity] = useState(45);

  useEffect(() => {
    setFloorLabels(buildFloorLabels(floors, basements));
  }, [floors, basements]);

  const drawing = footprint.length >= 3;
  const footprintArea = useMemo(() => shoelaceAreaM2(footprint), [footprint]);

  if (!isOpen) return null;

  const totalHeight = floors * floorHeight;

  const handleCopy = (id: string) => {
    navigator.clipboard?.writeText(id).catch(() => {});
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
    showToast('Copied 3D-ULPIN to clipboard');
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const res = await fileDetailedBuilderSubmission({
        project_name: projectName,
        parcel_ulpin: parcelUlpin,
        address: address || undefined,
        locality: locality || undefined,
        footprint_ring: drawing ? footprint : undefined,
        floor_labels: drawing ? floorLabels : undefined,
        builder_rera_id: reraId,
        municipal_sanction_no: sanctionNo,
        commencement_cert_date: ccDate,
        building_typology: typology,
        floors_above_ground: Number(floors),
        basements_count: Number(basements),
        floor_to_floor_height_m: Number(floorHeight),
        total_height_m: totalHeight,
        fsi_proposed: Number(fsi),
        setback_front_m: Number(setbackFront),
        setback_rear_m: Number(setbackRear),
        setback_side_north_m: Number(setbackNorth),
        setback_side_south_m: Number(setbackSouth),
        subsurface_depth_m: Number(subsurfaceDepth),
        sewer_invert_depth_m: Number(sewerDepth),
        stormwater_tank_m3: Number(stormwaterTank),
        rooftop_solar_capacity_kw: Number(solarCapacity),
      });
      setResult(res);
      showToast(
        drawing
          ? 'Drawn footprint persisted as builder-asserted geometry; submission pending review'
          : 'Detailed building submission filed; pending review'
      );
      onSuccess?.();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-canvas border-2 border-ink rounded-none shadow-brutal-xl max-w-3xl w-full max-h-[92vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-ink flex items-center justify-between bg-canvas">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-none bg-accent-faint border-2 border-ink flex items-center justify-center text-accent-strong">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-ink flex items-center gap-2">
                Detailed 3D Building Listing & Strata Sanction Studio
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-none bg-accent-faint text-accent-strong border-2 border-ink">
                  RERA · NBC 2016
                </span>
              </h2>
              <p className="text-xs text-ink-soft">
                Exhaustive architectural specifications, statutory clearances, and automated 3D-ULPIN minting
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-none flex items-center justify-center text-ink-soft hover:text-ink hover:bg-canvas transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {!result ? (
            <>
              {/* Tab navigation */}
              <div className="flex border-b border-ink gap-2">
                {[
                  { id: 'statutory', label: '1. Statutory & RERA' },
                  { id: 'massing', label: '2. 3D Massing & Setbacks' },
                  { id: 'utilities', label: '3. Subsurface & Solar' },
                  { id: 'preview', label: '4. Summary & Mint' },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id as any)}
                    className={`pb-2.5 px-3 text-xs font-bold transition border-b-2 ${
                      activeTab === t.id
                        ? 'border-ink text-accent-strong'
                        : 'border-ink text-ink-soft hover:text-ink'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {/* Tab 1: Statutory & RERA */}
              {activeTab === 'statutory' && (
                <div className="space-y-4 animate-fade-in">
                  <div className="p-3.5 rounded-none bg-accent-faint border-2 border-accent/15 text-xs text-ink">
                    <strong className="text-ink">These are the submitter's declarations.</strong> Nothing entered on this tab is checked against a registry, because none is reachable from this application. Quoting a number here records a claim; it does not evidence a registration, and acceptance by a reviewer is an internal workflow decision rather than a legal clearance.
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Project Name *</label>
                      <input
                        value={projectName}
                        onChange={(e) => setProjectName(e.target.value)}
                        placeholder="e.g. Emerald Horizon Towers"
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Parent Land ULPIN (14-char) *</label>
                      <input
                        value={parcelUlpin}
                        onChange={(e) => setParcelUlpin(e.target.value)}
                        placeholder="20260925001301"
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">RERA Project Registration No.</label>
                      <input
                        value={reraId}
                        onChange={(e) => setReraId(e.target.value)}
                        placeholder="Optional. Not verified against any registry."
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Municipal Sanction Proposal No.</label>
                      <input
                        value={sanctionNo}
                        onChange={(e) => setSanctionNo(e.target.value)}
                        placeholder="Optional. Not verified against any registry."
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Commencement Certificate Date</label>
                      <input
                        type="date"
                        value={ccDate}
                        onChange={(e) => setCcDate(e.target.value)}
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1 flex items-center gap-1">
                        <MapPin className="w-3 h-3 text-accent-strong" /> Address <span className="text-ink-mut font-normal">(persisted with the footprint)</span>
                      </label>
                      <input
                        value={address}
                        onChange={(e) => setAddress(e.target.value)}
                        placeholder="e.g. Plot 14, Riverside Avenue"
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Locality</label>
                      <input
                        value={locality}
                        onChange={(e) => setLocality(e.target.value)}
                        placeholder="e.g. Airoli"
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs text-ink outline-none focus:border-ink"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 2: 3D Massing & Setbacks */}
              {activeTab === 'massing' && (
                <div className="space-y-4 animate-fade-in">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Typology</label>
                      <select
                        value={typology}
                        onChange={(e) => setTypology(e.target.value)}
                        className="w-full bg-canvas border-2 border-ink rounded-none px-2.5 py-2 text-xs text-ink outline-none focus:border-ink"
                      >
                        <option value="tower">Residential Tower</option>
                        <option value="commercial">Commercial Plaza</option>
                        <option value="slab">Slab Building</option>
                        <option value="row_house">Garden Villas</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Above-Ground Floors</label>
                      <input
                        type="number"
                        min="1"
                        max="60"
                        value={floors}
                        onChange={(e) => setFloors(Number(e.target.value))}
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Basements</label>
                      <input
                        type="number"
                        min="0"
                        max="4"
                        value={basements}
                        onChange={(e) => setBasements(Number(e.target.value))}
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Floor Height (m)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={floorHeight}
                        onChange={(e) => setFloorHeight(Number(e.target.value))}
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                  </div>

                  {/* Footprint (SVG polygon editor) */}
                  <div className="p-3.5 rounded-none bg-canvas border-2 border-ink">
                    <div className="flex items-center gap-2 mb-1">
                      <PenTool className="w-3.5 h-3.5 text-accent-strong shrink-0" />
                      <span className="text-xs font-bold text-ink block">Building footprint (local metres)</span>
                      <Badge tone={drawing ? 'green' : 'amber'}>{drawing ? 'Ready to persist' : 'Below 3 vertices'}</Badge>
                    </div>
                    <p className="text-[10px] text-ink-mut mb-2">
                      No survey geometry for this parcel is reachable from here, so the polygon is exactly what the
                      submitter draws. It is recorded as <strong className="text-ink">builder-asserted, not surveyed</strong>,
                      and nothing else in the application will present it as a measured boundary.
                    </p>
                    <FootprintEditor points={footprint} onChange={setFootprint} />
                  </div>

                  {/* Per-floor names & uses */}
                  <div className="p-3.5 rounded-none bg-canvas border-2 border-ink">
                    <span className="text-xs font-bold text-ink block mb-1">
                      Per-floor names & uses ({floorLabels.length} levels)
                    </span>
                    <span className="text-[10px] text-ink-mut block mb-2">
                      Persisted as real level rows against the drawn footprint's structure. Editable here.
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                      {floorLabels.map((lv, i) => (
                        <div key={lv.level_code} className="flex items-center gap-1.5">
                          <code className="w-10 shrink-0 text-[10px] font-mono font-bold text-accent-strong">{lv.level_code}</code>
                          <input
                            value={lv.name}
                            onChange={(e) => {
                              const next = [...floorLabels];
                              next[i] = { ...next[i], name: e.target.value };
                              setFloorLabels(next);
                            }}
                            placeholder="Level name"
                            className="w-full bg-canvas border-2 border-ink rounded-none px-2 py-1 text-[11px] text-ink outline-none focus:border-ink"
                          />
                          <input
                            value={lv.use}
                            onChange={(e) => {
                              const next = [...floorLabels];
                              next[i] = { ...next[i], use: e.target.value };
                              setFloorLabels(next);
                            }}
                            placeholder="Use"
                            className="w-full bg-canvas border-2 border-ink rounded-none px-2 py-1 text-[11px] text-ink outline-none focus:border-ink"
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="pt-2">
                    <span className="block text-xs font-bold text-ink mb-2">NBC 2016 Fire & Evacuation Setbacks (metres)</span>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div>
                        <label className="block text-[10px] text-ink-soft mb-1">Front Setback (min 6.0m)</label>
                        <input
                          type="number"
                          step="0.1"
                          value={setbackFront}
                          onChange={(e) => setSetbackFront(Number(e.target.value))}
                          className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] text-ink-soft mb-1">Rear Setback (min 4.5m)</label>
                        <input
                          type="number"
                          step="0.1"
                          value={setbackRear}
                          onChange={(e) => setSetbackRear(Number(e.target.value))}
                          className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] text-ink-soft mb-1">Side North (min 4.5m)</label>
                        <input
                          type="number"
                          step="0.1"
                          value={setbackNorth}
                          onChange={(e) => setSetbackNorth(Number(e.target.value))}
                          className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] text-ink-soft mb-1">Side South (min 4.5m)</label>
                        <input
                          type="number"
                          step="0.1"
                          value={setbackSouth}
                          onChange={(e) => setSetbackSouth(Number(e.target.value))}
                          className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="p-3 bg-canvas border-2 border-ink rounded-none flex items-center justify-between text-xs">
                    <span className="text-ink-soft">Total Height: <strong className="text-ink font-mono">{totalHeight.toFixed(1)}m</strong></span>
                    <span className="text-ink-soft">High-rise threshold: <strong className="text-ink font-mono">15.0m</strong></span>
                    <Badge tone={totalHeight > 15 ? 'amber' : 'green'}>{totalHeight > 15 ? 'High Rise (>15m)' : 'Low Rise'}</Badge>
                  </div>
                </div>
              )}

              {/* Tab 3: Subsurface & Solar */}
              {activeTab === 'utilities' && (
                <div className="space-y-4 animate-fade-in">
                  <div className="p-3.5 rounded-none bg-canvas border-2 border-ink text-xs text-ink">
                    <strong>3D Subsurface & Air Rights Integration:</strong> Delineating underground utilities prevents catastrophic pipe clashes with municipal drainage and metro lines, while rooftop solar allocation assigns green air-rights quotas.
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Basement Foundation Depth (m)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={subsurfaceDepth}
                        onChange={(e) => setSubsurfaceDepth(Number(e.target.value))}
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Sewer Invert Level (m)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={sewerDepth}
                        onChange={(e) => setSewerDepth(Number(e.target.value))}
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Rainwater Tank Volume (m³)</label>
                      <input
                        type="number"
                        value={stormwaterTank}
                        onChange={(e) => setStormwaterTank(Number(e.target.value))}
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-ink mb-1">Rooftop Solar PV Quota (kWp)</label>
                      <input
                        type="number"
                        value={solarCapacity}
                        onChange={(e) => setSolarCapacity(Number(e.target.value))}
                        className="w-full bg-canvas border-2 border-ink rounded-none px-3 py-2 text-xs font-mono text-ink outline-none focus:border-ink"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 4: Summary & Mint */}
              {activeTab === 'preview' && (
                <div className="space-y-4 animate-fade-in">
                  <div className="p-4 rounded-none bg-canvas border-2 border-ink space-y-2 text-xs">
                    <div className="flex items-center justify-between pb-2 border-b border-ink">
                      <span className="font-bold text-ink text-sm">{projectName}</span>
                      <span className="font-mono text-xs text-accent-strong">{parcelUlpin}</span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-1 text-[11px]">
                      <div><span className="text-ink-soft">Typology:</span> <strong className="text-ink">{typology}</strong></div>
                      <div><span className="text-ink-soft">Floors:</span> <strong className="text-ink font-mono">{floors} above, {basements} below</strong></div>
                      <div><span className="text-ink-soft">Height:</span> <strong className="text-ink font-mono">{totalHeight}m</strong></div>
                      <div><span className="text-ink-soft">FSI:</span> <strong className="text-ink font-mono">{fsi}</strong></div>
                    </div>
                  </div>

                  <div className="p-3.5 rounded-none bg-accent-faint border-2 border-ink text-xs">
                    <span className="font-bold text-ink block">Strata identifier derivation</span>
                    {drawing ? (
                      <>
                        <span className="text-[11px] text-ink-soft">
                          A footprint was drawn ({footprint.length} vertices, {footprintArea.toFixed(1)} m² in local metres),
                          so {floorLabels.length} derived identifiers (one per level) will be <strong className="text-ink">persisted
                          against real Parcel/Structure/Level rows labelled builder-asserted, not surveyed</strong>.
                        </span>
                        <div className="mt-1.5 inline-flex items-center gap-1.5">
                          <code className="text-[10px] font-mono text-accent-strong">{address || '—'}, {locality || 'no locality'}</code>
                          {!drawing ? null : <Badge tone="green">PENDING_REVIEW</Badge>}
                        </div>
                      </>
                    ) : (
                      <span className="text-[11px] text-ink-soft">
                        No footprint drawn (<strong className="text-ink">need at least 3 vertices</strong>). The submission stays an
                        in-memory massing exercise: identifiers are computed but <strong className="text-ink">nothing is persisted</strong>,
                        and the record arrives PENDING_REVIEW until a reviewer accepts it.
                      </span>
                    )}
                    <div className="border-t border-ink/20 mt-2 pt-2 text-[10px] text-ink-mut">
                      These identifiers are workload labels for the proposed massing. They are not registry allocations
                      and confer no title.
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            /* Result Screen */
            <div className="space-y-5 animate-rise-in">
              <div className="p-5 rounded-none bg-canvas border-2 border-ink text-center">
                <div className="w-12 h-12 rounded-none bg-accent-faint border-2 border-ink text-ink-mut flex items-center justify-center mx-auto mb-2.5">
                  <ClipboardCheck className="w-6 h-6" />
                </div>
                <h3 className="text-base font-black text-ink">
                  Submitted for review
                </h3>
                <p className="text-xs text-ink-mut mt-1 max-w-md mx-auto">
                  {result.remarks}
                </p>
                <div className="mt-3 inline-flex items-center gap-2 font-mono text-xs font-bold text-ink px-3 py-1 rounded-none bg-chalk border-2 border-ink">
                  Submission ID: {result.submission_id} · {result.record_status}
                </div>
                <p className="text-[10px] text-ink-mut mt-2.5 max-w-md mx-auto text-left">
                  {result.record_basis}
                </p>
              </div>

              {/* Persisted footprint geometry, when one was drawn */}
              {result.asserted_geometry && (
                <div className="p-4 rounded-none bg-canvas border-2 border-ink">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-ink flex items-center gap-1.5">
                      <MapPin className="w-3.5 h-3.5 text-accent-strong" /> Persisted footprint geometry
                    </span>
                    <Badge tone={result.asserted_geometry.persistence.persisted ? 'green' : 'red'}>
                      {result.asserted_geometry.persistence.persisted ? 'Saved to registry DB' : 'Not persisted'}
                    </Badge>
                  </div>
                  <p className="text-[11px] font-bold text-ink mb-1">{result.asserted_geometry.basis}</p>
                  <p className="text-[11px] text-ink-mut">{result.asserted_geometry.note}</p>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] font-mono text-ink">
                    <span>structure: <strong className="text-accent-strong">{result.asserted_geometry.structure_code}</strong></span>
                    <span>vertices: <strong>{result.asserted_geometry.footprint_vertex_count}</strong></span>
                    <span>{address || ''}{address && locality ? ', ' : ''}{locality || ''}</span>
                  </div>
                  {!result.asserted_geometry.persistence.persisted && (
                    <p className="mt-2 text-[10px] text-red-700 bg-red-50 border border-red-200 rounded-none px-2 py-1.5">
                      {result.asserted_geometry.persistence.reason || 'The database was unavailable; nothing was written.'}
                    </p>
                  )}
                </div>
              )}

              {/* Advisory threshold comparison */}
              <div className="p-4 rounded-none bg-canvas border-2 border-ink">
                <span className="text-xs font-bold text-ink block mb-1">Advisory threshold comparison</span>
                <span className="text-[10px] text-ink-mut block mb-2">
                  {result.advisory_threshold_findings.note}
                </span>
                <div className="space-y-2">
                  {result.advisory_threshold_findings.checks.map((chk) => (
                    <div key={chk.check} className="flex items-center justify-between text-xs p-2 rounded-none bg-canvas border-2 border-ink">
                      <div>
                        <span className="font-bold text-ink block text-[11px]">{chk.label}</span>
                        <span className="text-[10px] text-ink-mut">Check: {chk.check} · Threshold: {chk.threshold}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-ink">{chk.provided}</span>
                        <Badge tone={chk.met ? 'green' : 'red'}>{chk.met ? 'MET' : 'NOT MET'}</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Minted 3D-ULPINs preview */}
              <div className="p-4 rounded-none bg-canvas border-2 border-ink">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-ink">
                    Derived strata identifiers ({result.minted_3d_ulpins.total_minted} total)
                  </span>
                </div>
                <p className="text-[10px] text-ink-mut mb-2">
                  {result.asserted_geometry
                    ? 'One identifier per submitted level. A level is not a unit: no strata units exist on this record, because nobody has subdivided it.'
                    : result.minted_3d_ulpins.identifier_note}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
                  {result.minted_3d_ulpins.units.map((u) => (
                    <div key={u.proposed_3d_id} className="p-2 rounded-none bg-canvas border-2 border-ink flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="text-[11px] font-bold text-ink">
                          {result.asserted_geometry ? `Level ${u.level_code}` : `Unit ${u.unit_number} (${u.level_code})`}
                        </span>
                        <code className="block text-[10px] font-mono text-accent-strong truncate">{u.proposed_3d_id}</code>
                        {u.carpet_area_m2 === null && (
                          <span className="block text-[9px] text-ink-mut italic">area not stated</span>
                        )}
                      </div>
                      <button
                        onClick={() => handleCopy(u.proposed_3d_id)}
                        className="text-ink-mut hover:text-accent-strong p-1"
                      >
                        {copiedId === u.proposed_3d_id ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-ink flex items-center justify-between bg-canvas">
          {!result ? (
            <>
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-bold text-ink-soft hover:text-ink transition"
              >
                Cancel
              </button>
              <div className="flex gap-2">
                {activeTab !== 'statutory' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (activeTab === 'preview') setActiveTab('utilities');
                      else if (activeTab === 'utilities') setActiveTab('massing');
                      else if (activeTab === 'massing') setActiveTab('statutory');
                    }}
                  >
                    Back
                  </Button>
                )}
                {activeTab !== 'preview' ? (
                  <Button
                    size="sm"
                    onClick={() => {
                      if (activeTab === 'statutory') setActiveTab('massing');
                      else if (activeTab === 'massing') setActiveTab('utilities');
                      else if (activeTab === 'utilities') setActiveTab('preview');
                    }}
                  >
                    Next Step →
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={handleSubmit}
                    disabled={submitting}
                    className="bg-accent hover:bg-accent/90 text-ink font-bold"
                  >
                    {submitting ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                        Running Audit & Minting...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                        Run NBC Audit & Mint 3D-ULPINs
                      </>
                    )}
                  </Button>
                )}
              </div>
            </>
          ) : (
            <div className="w-full flex justify-end">
              <Button
                onClick={() => {
                  setResult(null);
                  onClose();
                }}
                className="bg-ink hover:bg-ink/90 text-white font-bold text-xs"
              >
                Close Studio
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
