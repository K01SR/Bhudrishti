import React, { useEffect, useState } from 'react';
import { FileCheck2, FileText, AlertTriangle, Layers, Building2, Upload, FileCode, CheckCircle2, Box } from 'lucide-react';
import { Link } from 'react-router-dom';
import { fetchEvidenceStreams, fetchEpochChanges, ingestManualFloorplanTrace, ingestDxfFloorplan } from '../../services/api';
import { EvidenceStream } from '../../types/cadastre';
import { Card, Badge, StatusBadge, Skeleton, DemoHint, EmptyState } from '../../components/ui';
import { DEMO_ULPIN } from '../../constants';

export const EvidencePage: React.FC = () => {
  const [streams, setStreams] = useState<EvidenceStream[]>([]);
  const [epochData, setEpochData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [floorplanTab, setFloorplanTab] = useState<'sample' | 'upload'>('sample');
  const [parsingFloorplan, setParsingFloorplan] = useState(false);
  const [floorplanResult, setFloorplanResult] = useState<any | null>(null);
  const [floorplanError, setFloorplanError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchEvidenceStreams().catch((e) => { console.error('evidence', e); return []; }),
      fetchEpochChanges().catch((e) => { console.error('epoch changes', e); return null; }),
    ])
      .then(([s, ep]) => {
        if (!active) return;
        setStreams(s || []);
        setEpochData(ep);
      })
      .finally(() => active && setLoading(false));

    return () => {
      active = false;
    };
  }, []);

  const handleRunSampleTrace = async () => {
    setParsingFloorplan(true);
    setFloorplanError(null);
    try {
      const res = await ingestManualFloorplanTrace({
        unit_polygons: [
          [[0.0, 0.0], [14.0, 0.0], [14.0, 10.0], [0.0, 10.0], [0.0, 0.0]],
          [[14.0, 0.0], [28.0, 0.0], [28.0, 10.0], [14.0, 10.0], [14.0, 0.0]],
          [[0.0, 10.0], [14.0, 10.0], [14.0, 20.0], [0.0, 20.0], [0.0, 10.0]],
          [[14.0, 10.0], [28.0, 10.0], [28.0, 20.0], [14.0, 20.0], [14.0, 10.0]],
        ],
        parent_ulpin: DEMO_ULPIN,
        building_code: 'B17',
        level_code: 'L02',
        base_elevation_m: 7.2,
        floor_height_m: 3.6,
      });
      setFloorplanResult(res);
    } catch (err: any) {
      setFloorplanError(err.message || 'Floor plan extraction failed');
    } finally {
      setParsingFloorplan(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setParsingFloorplan(true);
    setFloorplanError(null);
    try {
      const res = await ingestDxfFloorplan(file, {
        parent_ulpin: DEMO_ULPIN,
        building_code: 'B17',
        level_code: 'L01',
        base_elevation_m: 3.6,
        floor_height_m: 3.6,
      });
      setFloorplanResult(res);
    } catch (err: any) {
      setFloorplanError(err.message || 'DXF parsing failed');
    } finally {
      setParsingFloorplan(false);
    }
  };

  return (
    <div className="flex flex-col gap-5 animate-rise-in">
      <div>
        <div className="flex items-center gap-2 annotation text-accent-strong">
          <span className="text-accent-strong">Reviewer (demo)</span><span>/</span><span>Evidence</span>
        </div>
        <h1 className="text-2xl font-black text-ink font-display tracking-tight mt-1">Evidence Ledger</h1>
        <p className="text-sm text-ink-soft mt-1">
          {/*
            Was the literal "Six ingested sources". A hardcoded count goes stale
            the moment a stream is added or the demo gate is shut, and then the
            page contradicts the list printed directly beneath it. Read the
            number instead.
          */}
          {loading
            ? 'Loading ingested sources.'
            : streams.length === 0
              ? 'No sources are currently ingested.'
              : `${streams.length} listed ${streams.length === 1 ? 'source' : 'sources'}. Each carries an explicit provenance statement and confidence tier. ${
                  streams.filter((s) => s.available).length === 0
                    ? 'None of them currently has data behind it.'
                    : ''
                }`}
        </p>
      </div>

      <div className="flex items-center gap-2">
        {/*
          Was a green "all hashes SHA-256" badge above a list of streams that
          have no file and no hash. The API returns no hash for any of them, so
          the badge asserted integrity that does not exist. Replaced with the
          count of what is actually available.
        */}
        <Badge tone={streams.some((s) => s.available) ? 'green' : 'amber'}>
          {streams.filter((s) => s.available).length} of {streams.length} sources available
        </Badge>
        <DemoHint />
      </div>

      {/* Multi-Epoch Change Detection & Volumetric Monitoring */}
      {epochData?.detection_result && (
        <Card className="p-5 border-ink bg-chalk via-white shadow-brutal-sm space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-amber-100">
            <div className="flex items-center gap-3">
              <span className="w-10 h-10 rounded-none bg-amber-100 border-2 border-ink flex items-center justify-center text-amber-800 shrink-0">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-ink">Multi-Epoch Volumetric Difference</h3>
                  <Badge tone="red">SYNTHETIC INPUTS</Badge>
                  <Badge tone="amber">
                    {epochData.detection_result.status}
                  </Badge>
                </div>
                <p className="text-xs text-ink-soft mt-0.5">
                  Comparing{' '}
                  <span className="font-bold text-ink">{epochData.detection_result.epoch_from}</span> and{' '}
                  <span className="font-bold text-ink">{epochData.detection_result.epoch_to}</span>.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Link
                to={`/app/properties/${epochData.parcel_ulpin}`}
                className="px-3 py-1.5 rounded-none bg-ink text-white text-xs font-bold hover:bg-ink-soft transition flex items-center gap-1"
              >
                <Building2 className="w-3.5 h-3.5" /> Inspect 3D Model →
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 bg-white rounded-none border-2 border-amber-100">
              <div className="text-[10px] text-ink-mut uppercase font-bold tracking-widest">Height Difference</div>
              <div className="text-xl font-black font-mono text-ink mt-1">
                {epochData.detection_result.delta_height_m >= 0 ? '+' : ''}
                {epochData.detection_result.delta_height_m}m
              </div>
              <div className="text-[11px] text-ink-soft">Between the two supplied values</div>
            </div>
            <div className="p-3 bg-white rounded-none border-2 border-amber-100">
              <div className="text-[10px] text-ink-mut uppercase font-bold tracking-widest">Floor Count Difference</div>
              <div className="text-xl font-black font-mono text-ink mt-1">
                {epochData.detection_result.delta_floors >= 0 ? '+' : ''}
                {epochData.detection_result.delta_floors}
              </div>
              <div className="text-[11px] text-ink-soft">Levels, not a compliance finding</div>
            </div>
            <div className="p-3 bg-white rounded-none border-2 border-amber-100">
              <div className="text-[10px] text-ink-mut uppercase font-bold tracking-widest">Volume Difference</div>
              <div className="text-xl font-black font-mono text-ink mt-1">
                {epochData.detection_result.delta_volume_m3} m³
              </div>
              <div className="text-[11px] text-ink-soft">Arithmetic over a synthetic footprint</div>
            </div>
            <div className="p-3 bg-white rounded-none border-2 border-amber-100">
              <div className="text-[10px] text-ink-mut uppercase font-bold tracking-widest">Target Parcel</div>
              <div className="text-xs font-bold font-mono text-ink mt-1 truncate">
                {epochData.parcel_ulpin}
              </div>
              <div className="text-[11px] text-ink-soft">{epochData.building_code}</div>
            </div>
          </div>

          {/* The evidentiary status, stated before the numbers rather than in a
              footnote. This used to render "+0.0m" and "Unauthorized level" in
              red against a real parcel number, which reads as a finding against
              a named building when there is no second survey anywhere on disk. */}
          <div className="p-3.5 rounded-none bg-crimson-50 border-2 border-crimson-600">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-crimson-700 shrink-0 mt-0.5" />
              <div className="space-y-1.5">
                <p className="text-xs font-bold text-crimson-800">
                  These figures are synthetic, not a finding
                </p>
                <p className="text-[11px] text-crimson-800 leading-relaxed">
                  {epochData.evidence_disclosure?.why_synthetic}
                </p>
                <p className="text-[11px] text-crimson-800 leading-relaxed">
                  {epochData.evidence_disclosure?.not_a_finding}
                </p>
                <details className="text-[11px] text-crimson-800">
                  <summary className="cursor-pointer font-bold">
                    What would make this a real finding
                  </summary>
                  <ul className="mt-1.5 space-y-0.5 pl-4 list-disc">
                    {(epochData.evidence_disclosure?.what_would_make_this_real || []).map((r: string) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </details>
              </div>
            </div>
          </div>

          {epochData.detection_result.detected_features && (
            <div className="p-3 rounded-none bg-canvas border-2 border-ink text-xs text-ink-soft flex items-start justify-between gap-3">
              <div className="flex items-start gap-2">
                <Layers className="w-4 h-4 text-ink-soft shrink-0 mt-0.5" />
                <div>
                  <span className="text-ink font-bold">Differences computed:</span>{' '}
                  {epochData.detection_result.detected_features.join('; ')}.
                  {epochData.detection_result.wording_note && (
                    <p className="mt-1 text-[11px]">{epochData.detection_result.wording_note}</p>
                  )}
                </div>
              </div>
              <span className="text-[10px] font-mono text-ink-mut shrink-0">API: GET /changes/compare</span>
            </div>
          )}
        </Card>
      )}

      {/* Floor Plan Ingestion Pipeline (CAD DXF & Vector Trace) */}
      <Card className="p-5 border-ink bg-surface shadow-brutal-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-ink">
          <div className="flex items-center gap-3">
            <span className="w-10 h-10 rounded-none bg-accent-faint border-2 border-ink flex items-center justify-center text-accent-strong shrink-0">
              <Building2 className="w-5 h-5 text-accent-strong" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-ink text-sm">Architectural Floor Plan Ingestion &amp; 3D Strata Delineation</h3>
                <Badge tone="purple">LADM ISO 19152</Badge>
              </div>
              <p className="text-xs text-ink-soft">
                Converts AutoCAD/LibreCAD DXF polylines or surveyor polygon traces into volumetric 3D units with automated carpet area computation and 3D-ULPIN minting.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 p-1 bg-canvas rounded-none border-2 border-ink">
            <button
              onClick={() => { setFloorplanTab('sample'); setFloorplanError(null); }}
              className={`px-3 py-1 text-xs font-bold rounded-none transition ${
                floorplanTab === 'sample' ? 'bg-surface text-ink shadow-xs border-2 border-ink' : 'text-ink-soft hover:text-ink'
              }`}
            >
              Vector Trace
            </button>
            <button
              onClick={() => { setFloorplanTab('upload'); setFloorplanError(null); }}
              className={`px-3 py-1 text-xs font-bold rounded-none transition ${
                floorplanTab === 'upload' ? 'bg-surface text-ink shadow-xs border-2 border-ink' : 'text-ink-soft hover:text-ink'
              }`}
            >
              Upload CAD DXF
            </button>
          </div>
        </div>

        {floorplanTab === 'sample' ? (
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded-none bg-canvas border-2 border-ink text-xs">
            <div className="space-y-1">
              <div className="font-bold text-ink flex items-center gap-1.5">
                <FileCode className="w-4 h-4 text-accent-strong" />
                <span>Sample Architectural Ingestion (Building B-17, Level 02)</span>
              </div>
              <p className="text-ink-soft text-[11px]">
                Four residential units (2BHK / 3BHK layout) on Level 2 with base elevation 7.2m and floor height 3.6m.
              </p>
            </div>
            <button
              onClick={handleRunSampleTrace}
              disabled={parsingFloorplan}
              className="px-4 py-2 bg-accent text-ink text-xs font-bold rounded-none hover:bg-accent/90 transition disabled:opacity-50 shrink-0 flex items-center gap-2"
            >
              {parsingFloorplan ? (
                <span>Extruding 3D Units...</span>
              ) : (
                <>
                  <Box className="w-3.5 h-3.5" />
                  <span>Execute Vector Trace &amp; Extrude</span>
                </>
              )}
            </button>
          </div>
        ) : (
          <div className="p-4 rounded-none bg-canvas border-2 border-ink space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-ink">
              <Upload className="w-4 h-4 text-accent-strong" />
              <span>Upload AutoCAD / Architectural DXF (.dxf)</span>
            </div>
            <p className="text-[11px] text-ink-soft">
              Ingests closed polylines (LWPOLYLINE / POLYLINE) representing unit footprints. Auto-normalizes millimeter CAD coordinates to meters.
            </p>
            <div className="flex items-center gap-3">
              <input
                type="file"
                accept=".dxf"
                onChange={handleFileUpload}
                disabled={parsingFloorplan}
                className="text-xs text-ink-soft file:mr-3 file:py-1.5 file:px-3 file:rounded-none file:border-0 file:text-xs file:font-bold file:bg-accent file:text-ink hover:file:bg-accent/90 cursor-pointer"
              />
              {parsingFloorplan && <span className="text-xs text-ink-soft">Parsing DXF entities...</span>}
            </div>
          </div>
        )}

        {floorplanError && (
          <div className="p-3 rounded-none bg-rose-50 border-2 border-ink text-xs text-rose-800 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{floorplanError}</span>
          </div>
        )}

        {floorplanResult && (
          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-emerald-800">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>Extrusion Complete — {floorplanResult.total_units_extruded} Strata Units Generated</span>
              </div>
              <Badge tone="green">3D-ULPIN Active</Badge>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3 bg-canvas rounded-none border-2 border-ink">
                <div className="text-[10px] text-ink-mut uppercase font-bold tracking-widest">Units Extruded</div>
                <div className="text-xl font-black font-mono text-ink mt-1">{floorplanResult.total_units_extruded}</div>
                <div className="text-[11px] text-ink-soft">{floorplanResult.level_code} (Z: {floorplanResult.base_elevation_m}m)</div>
              </div>
              <div className="p-3 bg-canvas rounded-none border-2 border-ink">
                <div className="text-[10px] text-ink-mut uppercase font-bold tracking-widest">Total Built-Up Area</div>
                <div className="text-xl font-black font-mono text-ink mt-1">{floorplanResult.total_built_up_area_m2} m²</div>
                <div className="text-[11px] text-ink-soft">Gross footprint sum</div>
              </div>
              <div className="p-3 bg-canvas rounded-none border-2 border-ink">
                <div className="text-[10px] text-ink-mut uppercase font-bold tracking-widest">Total Carpet Area</div>
                <div className="text-xl font-black font-mono text-emerald-700 mt-1">{floorplanResult.total_carpet_area_m2} m²</div>
                <div className="text-[11px] text-ink-soft">Net usable area (88%)</div>
              </div>
              <div className="p-3 bg-canvas rounded-none border-2 border-ink">
                <div className="text-[10px] text-ink-mut uppercase font-bold tracking-widest">Total Volume</div>
                <div className="text-xl font-black font-mono text-accent-strong mt-1">{floorplanResult.total_volume_m3} m³</div>
                <div className="text-[11px] text-ink-soft">Height: {floorplanResult.floor_height_m}m</div>
              </div>
            </div>

            <div className="overflow-x-auto rounded-none border-2 border-ink">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-canvas border-b border-ink text-left text-ink-mut uppercase text-[10px] font-bold">
                    <th className="py-2.5 px-3">Unit</th>
                    <th className="py-2.5 px-3">Assigned 3D-ULPIN</th>
                    <th className="py-2.5 px-3 text-right">Carpet Area</th>
                    <th className="py-2.5 px-3 text-right">Built-Up Area</th>
                    <th className="py-2.5 px-3 text-right">Volume</th>
                    <th className="py-2.5 px-3 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink/10 bg-surface">
                  {floorplanResult.extruded_units?.map((u: any, idx: number) => (
                    <tr key={idx} className="hover:bg-canvas/50">
                      <td className="py-2.5 px-3 font-bold text-ink">
                        {u.unit_id || `Unit ${idx + 1}`}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-accent-strong">
                        {u.ulpin_3d}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-right text-emerald-700">
                        {u.carpet_area_m2} m²
                      </td>
                      <td className="py-2.5 px-3 font-mono text-right text-ink">
                        {u.built_up_area_m2} m²
                      </td>
                      <td className="py-2.5 px-3 font-mono text-right text-ink-soft">
                        {u.volume_m3} m³
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-none text-[10px] font-bold bg-emerald-100 text-emerald-800">
                          Extruded
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-44 rounded-none" />)}
        </div>
      ) : streams.length === 0 ? (
        <Card>
          <EmptyState icon={<FileCheck2 className="w-5 h-5" />} title="No evidence streams" description="The ledger is empty for this demo session." />
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {streams.map((s) => (
            <Card key={s.id} className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <span className="w-9 h-9 rounded-none bg-canvas border-2 border-ink flex items-center justify-center text-accent-strong shrink-0">
                    <FileText className="w-4 h-4" />
                  </span>
                  <div>
                    <div className="text-xs font-bold text-ink">{s.name}</div>
                    <div className="font-mono text-[10px] text-ink-mut">{s.id} · {s.source_type}</div>
                  </div>
                </div>
                <StatusBadge status={s.available ? 'ACTIVE' : 'NOT AVAILABLE'} className="text-[9px]" />
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="slate">tier: {s.confidence_tier}</Badge>
                {s.format && <Badge tone="sky">{s.format}</Badge>}
              </div>

              {/*
                Provenance is the field that matters and it was never shown.
                The API already stated plainly that these are unsourced, and the
                card used to show an empty tag cell instead.
              */}
              <div className="text-[11px] leading-relaxed bg-canvas border-2 border-ink px-2.5 py-2">
                <span className="font-bold text-ink">Provenance: </span>
                <span className="text-ink-soft">{s.provenance}</span>
              </div>

              {s.provenance_note && (
                <div className="text-[11px] leading-relaxed text-ink-soft bg-accent-faint border-2 border-ink px-2.5 py-2">
                  {s.provenance_note}
                </div>
              )}

              <div className="space-y-1.5 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-ink-soft">CRS</span>
                  <span className="font-mono text-[11px] text-ink">{s.crs ?? 'not established'}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-ink-soft">Quality</span>
                  <span className="text-[11px] text-ink text-right">{s.quality_result}</span>
                </div>
              </div>

              <div className="text-[11px] leading-relaxed bg-canvas border-2 border-ink px-2.5 py-2">
                <span className="font-bold text-ink">To activate: </span>
                <span className="text-ink-soft">{s.required_to_activate}</span>
              </div>
            </Card>
          ))}
        </div>
      )}

      <div className="text-[11px] text-ink-soft">
        <Link to={`/app/properties/${DEMO_ULPIN}`} className="text-accent-strong font-bold hover:underline">Open Building B-17 evidence tab →</Link>
      </div>
    </div>
  );
};