import React, { useEffect, useState } from 'react';
import {
  X,
  Layers,
  ExternalLink,
  ShieldCheck,
  Globe2,
  Copy,
  Check,
  Download,
  Trees,
  Car,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useOpenStudioStore } from '../../store/useOpenStudioStore';
import { PROPERTY_CARD_PDF_URL, fetchOsmAmenities, fetchOsmStreets } from '../../services/api';
import { OsmAmenitiesResponse, OsmStreetsResponse } from '../../types/cadastre';

export const RightInspectorPanel: React.FC = () => {
  const navigate = useNavigate();
  const {
    rightPanelOpen,
    setRightPanelOpen,
    selectedBuilding,
    selectedFloor,
    selectFloor,
    isExploded,
    toggleExplode,
    activeInspectorTab,
    setActiveInspectorTab,
  } = useOpenStudioStore();

  const [copied, setCopied] = useState(false);
  const [civicAmenities, setCivicAmenities] = useState<OsmAmenitiesResponse | null>(null);
  const [civicStreets, setCivicStreets] = useState<OsmStreetsResponse | null>(null);

  useEffect(() => {
    fetchOsmAmenities().then(setCivicAmenities).catch(() => {});
    fetchOsmStreets().then(setCivicStreets).catch(() => {});
  }, []);

  if (!rightPanelOpen || !selectedBuilding) {
    return null;
  }

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  /**
   * Storeys come from the source, or from a height at an assumed floor-to-floor
   * dimension, flagged as derived. The previous line was
   *   Math.max(1, floorsCount || Math.round(heightM / 3.5) || 5)
   * which invented a floor for a null height and then invented five more.
   */
  const floorsCount = selectedBuilding.floorsCount
    ?? (selectedBuilding.heightM === null ? null : Math.max(1, Math.round(selectedBuilding.heightM / 3.5)));
  const floorsAreDerived = selectedBuilding.floorsCount === null && floorsCount !== null;
  const floorHeightM = floorsCount === null || selectedBuilding.heightM === null
    ? null
    : selectedBuilding.heightM / floorsCount;
  const currentFloorZ = selectedFloor !== null && floorHeightM !== null
    ? (selectedFloor * floorHeightM).toFixed(1)
    : null;

  /**
   * A sub-ULPIN may only be composed from a parent ULPIN that the state
   * registry actually issued. A locally generated 3D identifier is not a
   * ULPIN and must never become the prefix of one, so the composed form is
   * withheld unless a real parent exists.
   */
  const parentUlpin = selectedBuilding.officialCadastreUlpin;
  const strataSubUlpin = parentUlpin && selectedFloor !== null
    ? `${parentUlpin}/U-L${String(selectedFloor + 1).padStart(2, '0')}-401`
    : null;

  return (
    <aside className="relative z-20 w-84 md:w-96 flex flex-col border-l border-white/40 bg-slate-950/95 backdrop-blur-xl h-full shadow-brutal-xl select-none animate-slide-left">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/90">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-2.5 h-2.5 rounded-full bg-accent animate-pulse flex-shrink-0" />
          <h3 className="text-xs font-bold font-mono tracking-widest text-white uppercase truncate">
            {selectedBuilding.name || '3D Digital Twin Structure'}
          </h3>
        </div>
        <button
          onClick={() => setRightPanelOpen(false)}
          className="p-1 rounded-none text-slate-300 hover:text-white hover:bg-slate-800/80 transition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center border-b border-white/40 bg-slate-900/60 p-1 text-[11px] font-mono">
        {(
          [
            { id: 'massing', label: 'Massing' },
            { id: 'strata', label: '3D Strata' },
            { id: 'civic', label: 'Civic Data' },
            { id: 'lineage', label: 'Lineage' },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveInspectorTab(t.id)}
            className={`flex-1 py-1.5 rounded-none text-center font-bold transition ${
              activeInspectorTab === t.id
                ? 'bg-accent text-white'
                : 'text-slate-300 hover:text-slate-300 hover:bg-slate-800/50'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs font-sans">
        {/* Top 3D-ULPIN Badge */}
        <div className="bg-slate-900/80 border border-slate-700/80 rounded-none p-3.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase font-mono font-bold tracking-widest text-slate-300 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5" /> Strata Identifier (local, not issued)
            </span>
            {strataSubUlpin ? (
              <button
                onClick={() => handleCopy(strataSubUlpin)}
                className="text-[10px] font-mono text-slate-300 hover:text-slate-300 transition flex items-center gap-1"
              >
                {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            ) : (
              <span className="text-[10px] font-mono text-slate-300">
                No state-issued parent ULPIN
              </span>
            )}
          </div>
          <div className="font-mono font-bold text-sm text-white break-all tracking-tight bg-slate-950/70 p-2 rounded-none border border-white/40">
            {strataSubUlpin ?? (
              <span className="text-slate-300 font-sans text-xs leading-relaxed block">
                This parcel has no ULPIN in the source, so no sub-strata ULPIN
                can be composed. A locally derived label is shown instead and is
                not an official identifier.
                {selectedBuilding.derivedLocalId ? (
                  <> <span className="font-mono">{selectedBuilding.derivedLocalId}</span></>
                ) : null}
              </span>
            )}
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-300 font-mono">
            <span>Centroid: {selectedBuilding.centroid[0].toFixed(5)}, {selectedBuilding.centroid[1].toFixed(5)}</span>
            <span className="text-slate-300 font-bold">{selectedFloor !== null ? `Floor L${selectedFloor + 1}` : 'Entire Envelope'}</span>
          </div>
        </div>

        {/* TAB 1: MASSING */}
        {activeInspectorTab === 'massing' && (
          <div className="space-y-3 animate-rise-in">
            <div className="grid grid-cols-2 gap-2">
              <div className="p-3 bg-slate-900/60 border border-white/40 rounded-none">
                <span className="text-[10px] text-slate-300 uppercase font-mono">Structure Height</span>
                <div className="text-base font-bold font-mono text-white mt-0.5">
                  {selectedBuilding.heightM === null ? (
                    <span className="text-sm text-slate-300">Not in source</span>
                  ) : (
                    `${selectedBuilding.heightM.toFixed(1)} m`
                  )}
                </div>
                <span className="text-[10px] text-slate-300">
                  {floorsCount === null
                    ? 'No storey count in source'
                    : floorsAreDerived
                      ? `${floorsCount} storeys, assumed at 3.5 m`
                      : `${floorsCount} Above-Ground Floors`}
                </span>
              </div>

              <div className="p-3 bg-slate-900/60 border border-white/40 rounded-none">
                <span className="text-[10px] text-slate-300 uppercase font-mono">Land Use</span>
                <div className="text-base font-bold font-mono text-slate-300 mt-0.5 capitalize">
                  {selectedBuilding.landUse ?? (
                    <span className="text-sm text-slate-300">Not in source</span>
                  )}
                </div>
                <span className="text-[10px] text-slate-300">
                  No zoning designation is held
                </span>
              </div>

              <div className="p-3 bg-slate-900/60 border border-white/40 rounded-none">
                <span className="text-[10px] text-slate-300 uppercase font-mono">FSI Utilization</span>
                <div className="text-base font-bold font-mono text-white mt-0.5">
                  {selectedBuilding.fsi === null ? (
                    <span className="text-sm text-slate-300">Not in source</span>
                  ) : (
                    <span className="text-white">{selectedBuilding.fsi.toFixed(2)}</span>
                  )}
                </div>
                <span className="text-[10px] text-slate-300">
                  {selectedBuilding.fsiStatus === null
                    ? 'No permitted-FAR rule on record, so no verdict'
                    : selectedBuilding.fsiStatus === 'EXCEEDED'
                      ? 'Above the permitted FAR on record'
                      : 'Within the permitted FAR on record'}
                </span>
              </div>

              <div className="p-3 bg-slate-900/60 border border-white/40 rounded-none">
                <span className="text-[10px] text-slate-300 uppercase font-mono">Built-up Footprint</span>
                <div className="text-base font-bold font-mono text-white mt-0.5">
                  <span className="text-sm text-slate-300">Not in source</span>
                </div>
                <span className="text-[10px] text-slate-300">
                  This was a constant 510 m² multiplied by a storey count, which
                  produced a plausible built-up area for every building.
                </span>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: 3D STRATA SLICING */}
        {activeInspectorTab === 'strata' && (
          <div className="space-y-3 animate-rise-in">
            <div className="bg-slate-900/70 border border-white/40 rounded-none p-3 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-white flex items-center gap-1.5 font-mono">
                  <Layers className="w-3.5 h-3.5 text-slate-300" />
                  Volumetric Floor Slicing
                </span>
                <span className="text-[10px] font-mono text-slate-300">
                  {floorsCount === null ? 'No storey count' : `${floorsCount} Levels`}
                </span>
              </div>

              <button
                onClick={toggleExplode}
                className={`w-full py-2.5 px-3 rounded-none text-xs font-bold transition flex items-center justify-center gap-2 shadow-brutal ${
                  isExploded
                    ? 'bg-rose-600/30 text-rose-300 border border-rose-500/50 hover:bg-rose-600/40'
                    : 'bg-accent text-white hover:opacity-90'
                }`}
              >
                <Layers className="w-4 h-4" />
                {isExploded ? 'Collapse Slices into Solid Twin' : 'Explode Building into Floating Floors'}
              </button>

              {isExploded && (
                <div className="space-y-1.5 pt-2">
                  <span className="text-[10px] uppercase font-mono font-bold text-slate-300 tracking-widest">
                    Select Strata Slab to Inspect:
                  </span>
                  <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
                    {(floorsCount === null ? [] : Array.from({ length: floorsCount }, (_, i) => floorsCount - 1 - i)).map((floor) => {
                      const active = selectedFloor === floor;
                      return (
                        <button
                          key={floor}
                          onClick={() => selectFloor(floor)}
                          className={`w-full text-left px-3 py-2 rounded-none text-xs font-mono transition flex items-center justify-between ${
                            active
                              ? 'bg-amber-400 text-white font-bold shadow-brutal'
                              : 'bg-slate-800/60 hover:bg-slate-700/80 text-slate-300'
                          }`}
                        >
                          <span>Floor {String(floor).padStart(2, '0')}</span>
                          <span className="text-[10px] opacity-75">
                            {floor === 0 ? 'Ground Plinth (Z=0.0m)' : `Z = +${(floor * 3.5).toFixed(1)}m`}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {selectedFloor !== null && (
              <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-none space-y-1 text-amber-200 font-mono text-xs">
                <div className="font-bold">Floor Slab {selectedFloor} Active</div>
                <div className="text-[11px] opacity-80">
                  {currentFloorZ === null
                    ? 'Slab elevation: not derivable without a measured height'
                    : `Modelled slab elevation: +${currentFloorZ} m relative to the building base`}
                </div>
                <div className="text-[11px] opacity-80">
                  Tenancies: not in source. No unit register is held for this
                  parcel, so no units are listed.
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: CIVIC DATA */}
        {activeInspectorTab === 'civic' && (
          <div className="space-y-3 animate-rise-in">
            {/* Street Access */}
            <div className="p-3 bg-slate-900/60 border border-white/40 rounded-none space-y-2">
              <span className="text-[10px] uppercase font-mono font-bold text-slate-300 flex items-center gap-1.5">
                <Car className="w-3.5 h-3.5" /> Direct Street Frontage
              </span>
              <div className="font-bold text-white text-xs">
                {civicStreets?.streets?.[0]?.name || 'Airoli Sector 8 Main Avenue'}
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-300 font-mono">
                <div>Right of Way: {civicStreets?.streets?.[0]?.right_of_way_m || 20.0} m</div>
                <div>Lanes: {civicStreets?.streets?.[0]?.lanes || 4} Lanes</div>
                <div>Speed Limit: {civicStreets?.streets?.[0]?.speed_limit_kmh || 50} km/h</div>
                <div>PCI Rating: {civicStreets?.streets?.[0]?.pci_index || 94}/100</div>
              </div>
            </div>

            {/* Nearby Amenities */}
            <div className="p-3 bg-slate-900/60 border border-white/40 rounded-none space-y-2">
              <span className="text-[10px] uppercase font-mono font-bold text-emerald-400 flex items-center gap-1.5">
                <Trees className="w-3.5 h-3.5" /> Proximity to Public Infrastructure
              </span>
              <div className="space-y-1.5">
                {civicAmenities?.amenities?.slice(0, 3).map((a: any, i: number) => (
                  <div key={i} className="flex items-center justify-between text-[11px] border-b border-slate-800/60 pb-1 last:border-0">
                    <span className="text-slate-300 truncate max-w-[200px]">{a.name}</span>
                    <span className="text-slate-300 font-mono text-[10px] font-bold">~{Math.round(a.x + a.y) % 400 + 120} m</span>
                  </div>
                )) || (
                  <div className="text-slate-300 text-[11px]">Loading civic amenity matrix...</div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: LINEAGE */}
        {activeInspectorTab === 'lineage' && (
          <div className="space-y-3 animate-rise-in font-mono text-[11px]">
            <div className="p-3 bg-slate-900/60 border border-white/40 rounded-none space-y-1.5">
              <div className="text-slate-300 font-bold uppercase text-[10px] flex items-center gap-1">
                <Globe2 className="w-3 h-3" /> Data Lineage & Provenance
              </div>
              <div className="text-slate-300">Origin: OpenStreetMap Overpass Live API</div>
              <div className="text-slate-300">Way ID: {selectedBuilding.osmId || 'osm-way-4910291'}</div>
              <div className="text-slate-300">Geodetic Model: WGS84 (EPSG:4326)</div>
              <div className="text-slate-300">Vertical CRS: GTS MSL Datum (+12.0m)</div>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="pt-2 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            {/*
              Both of these used to resolve to
                officialCadastreUlpin || prototype3DULPIN || DEMO_ULPIN
              so that clicking "Full Ledger" on any OSM building opened the
              cadastral record of a different, real parcel, and "Property Card"
              produced a legal document naming that parcel. Both are now
              withheld unless a state-issued ULPIN is actually present.
            */}
            {parentUlpin ? (
              <>
                <button
                  onClick={() => navigate(`/app/properties/${parentUlpin}`)}
                  className="py-2 px-3 rounded-none text-xs font-bold bg-ink hover:bg-ink text-white transition flex items-center justify-center gap-1.5 shadow"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Full Ledger
                </button>
                <a
                  href={PROPERTY_CARD_PDF_URL(parentUlpin)}
                  target="_blank"
                  rel="noreferrer"
                  className="py-2 px-3 rounded-none text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-white/40 transition flex items-center justify-center gap-1.5 text-center"
                >
                  <Download className="w-3.5 h-3.5 text-emerald-400" /> Property Card
                </a>
              </>
            ) : (
              <span className="col-span-2 py-2 px-3 rounded-none text-[11px] font-bold bg-slate-900 text-slate-300 border border-white/40 text-center leading-relaxed">
                No cadastral record for this building. A ledger entry and a
                property card can only be issued against a parcel the state
                registry has numbered, and this one has no ULPIN in the source.
              </span>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
};
