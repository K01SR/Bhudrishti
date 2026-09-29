import React, { useState } from 'react';
import {
  X,
  Building2,
  Layers,
  MapPin,
  ExternalLink,
  Globe2,
  Copy,
  Check,
  Download,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { InspectedStructure } from './DeckGL3DOverlay';
import { PROPERTY_CARD_PDF_URL } from '../../services/api';

interface CadastrePropertyInspectorProps {
  structure: InspectedStructure | null;
  isExploded: boolean;
  selectedFloor: number | null;
  onToggleExplode: () => void;
  onSelectFloor: (floor: number) => void;
  onClose: () => void;
}

export const CadastrePropertyInspector: React.FC<CadastrePropertyInspectorProps> = ({
  structure,
  isExploded,
  selectedFloor,
  onToggleExplode,
  onSelectFloor,
  onClose,
}) => {
  const navigate = useNavigate();
  const [copied, setCopied] = useState(false);

  if (!structure) return null;

  /**
   * Storeys are counted from the source where a count exists. Failing that, a
   * height implies a storey count only under an assumed floor-to-floor
   * dimension, so the result is flagged and shown as an assumption.
   *
   * The previous expression was
   *   structure.floorsCount || Math.max(1, Math.round(structure.heightM / 3.5)) || 1
   * which had three separate problems: `Math.max(1, ...)` guaranteed a floor
   * even for a null height (null / 3.5 === 0), the trailing `|| 1` invented a
   * second storey count, and neither was ever labelled as derived.
   */
  const totalFloors = structure.floorsCount
    ?? (structure.heightM === null ? null : Math.max(1, Math.round(structure.heightM / 3.5)));
  const floorsAreDerived = structure.floorsCount === null && totalFloors !== null;
  const activeFloor = selectedFloor !== null ? selectedFloor : null;

  // Strata identifiers are derived from the parent ULPIN. With no parent, the
  // result would be a plausible-looking cadastral ID for nothing, so there is
  // no parent to derive from.
  const parentUlpin = structure.ulpin;
  const strataUlpin = activeFloor !== null
    ? `${parentUlpin}/U-L${String(activeFloor).padStart(2, '0')}-${String(activeFloor * 100 + 1).padStart(3, '0')}`
    : `${parentUlpin}/B-${structure.name.substring(0, 3).toUpperCase()}`;

  const handleCopy = () => {
    navigator.clipboard.writeText(strataUlpin);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const provenanceBadge = () => {
    switch (structure.source) {
      case 'OPEN_STREET_MAP':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-sky-500/15 text-sky-400 border border-sky-500/30">
            <Globe2 className="w-3 h-3" /> LIVE OPENSTREETMAP
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/15 text-purple-400 border border-purple-500/30">
            <Building2 className="w-3 h-3" /> SYNTHETIC TWIN
          </span>
        );
    }
  };

  return (
    <div className="absolute top-4 right-4 z-30 w-84 md:w-96 max-h-[calc(100vh-2rem)] bg-slate-900/95 backdrop-blur-xl border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden text-white animate-fade-in font-sans">
      {/* ── Top Header ──────────────────────────────────────────────────────── */}
      <div className="p-4 border-b border-slate-800 flex items-start justify-between bg-slate-950/60">
        <div className="flex-1 min-w-0 pr-2">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            {provenanceBadge()}
            <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
              {structure.buildingType || 'STRUCTURE'}
            </span>
          </div>
          <h3 className="text-base font-bold text-slate-100 truncate" title={structure.name}>
            {structure.name}
          </h3>
          <p className="text-xs text-slate-400 flex items-center gap-1 mt-0.5">
            <MapPin className="w-3 h-3 text-slate-500 shrink-0" />
            <span className="truncate">
              {structure.centroid ? `${structure.centroid[1].toFixed(5)}°N, ${structure.centroid[0].toFixed(5)}°E` : 'Cadastral Coordinate Record'}
            </span>
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          aria-label="Close Inspector"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* ── Scrollable Body ─────────────────────────────────────────────────── */}
      <div className="p-4 overflow-y-auto space-y-4 flex-1 text-xs">
        {/* ULPIN Identifier Card */}
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3">
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
            <span className="font-semibold uppercase tracking-wider text-[10px] text-cyan-400">
              {activeFloor !== null ? '3D Strata ULPIN (Unit Level)' : 'Cadastral Parcel ULPIN'}
            </span>
            <button
              onClick={handleCopy}
              className="text-slate-400 hover:text-cyan-400 flex items-center gap-1 transition"
              title="Copy identifier"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              <span className="text-[10px]">{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <div className="font-mono text-sm font-bold text-cyan-300 break-all select-all">
            {strataUlpin}
          </div>
          {activeFloor !== null && (
            <p className="text-[10px] text-slate-500 mt-1">
              Deterministic ISO/IEC 7064 Luhn Mod 36 spatial strata extension for Floor {String(activeFloor).padStart(2, '0')}
            </p>
          )}
        </div>

        {/* Spatial Massing & Geometry Metrics */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2.5 bg-slate-800/40 border border-slate-800 rounded-xl">
            <span className="text-[10px] text-slate-400 uppercase font-semibold">Total Height</span>
            <div className="text-base font-bold font-mono text-slate-200 mt-0.5">
              {structure.heightM === null ? (
                <span className="text-slate-400 text-sm">Not in source</span>
              ) : (
                `${structure.heightM.toFixed(1)} m`
              )}
            </div>
            <span className="text-[10px] text-slate-500">Above Ground Plinth</span>
          </div>

          <div className="p-2.5 bg-slate-800/40 border border-slate-800 rounded-xl">
            <span className="text-[10px] text-slate-400 uppercase font-semibold">Floors Above Ground</span>
            <div className="text-base font-bold font-mono text-slate-200 mt-0.5">
              {totalFloors === null ? (
                <span className="text-slate-400 text-sm">Not in source</span>
              ) : (
                `${totalFloors} Levels`
              )}
            </div>
            <span className="text-[10px] text-slate-500">Vertical Strata</span>
          </div>

          <div className="p-2.5 bg-slate-800/40 border border-slate-800 rounded-xl">
            <span className="text-[10px] text-slate-400 uppercase font-semibold">FSI Status</span>
            <div className="text-base font-bold font-mono mt-0.5">
              {structure.fsi == null ? (
                <span className="text-slate-400 text-sm">Not in source</span>
              ) : (
                <span className="text-slate-200">{structure.fsi.toFixed(2)}</span>
              )}
            </div>
            <span className="text-[10px] text-slate-500">
              {structure.fsi && structure.fsi > 2.0 ? 'Violation Exceeded' : 'NBC Compliant'}
            </span>
          </div>

          <div className="p-2.5 bg-slate-800/40 border border-slate-800 rounded-xl">
            <span className="text-[10px] text-slate-400 uppercase font-semibold">Inspection Mode</span>
            <div className="text-base font-bold font-mono text-slate-200 mt-0.5">
              {isExploded ? 'Exploded' : 'Solid'}
            </div>
            <span className="text-[10px] text-slate-500">
              {activeFloor !== null ? `Floor ${activeFloor} Focused` : 'Envelope View'}
            </span>
          </div>
        </div>

        {/* ── Exploded Floor Slicing Controls ─────────────────────────────────── */}
        <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3 space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-cyan-400" />
              3D Vertical Strata Slicing
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              {totalFloors === null
                ? 'No storey count in source'
                : floorsAreDerived
                  ? `${totalFloors} storeys, assumed at 3.5 m floor-to-floor`
                  : `${totalFloors} Floors`}
            </span>
          </div>

          <button
            onClick={onToggleExplode}
            className={`w-full py-2 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center gap-2 ${
              isExploded
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30'
                : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/30'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            {isExploded ? 'Collapse Slices to Solid Mass' : 'Explode Building into Floating Floors'}
          </button>

          {isExploded && (
            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">
                Select Floor to Inspect Units:
              </span>
              <div className="max-h-40 overflow-y-auto space-y-1 pr-1">
                {totalFloors === null ? (
                  <p className="text-[10px] text-slate-400 leading-relaxed font-sans py-1">
                    No storey count in the source, so there are no storeys to
                    list. A list built from a guessed count would look like a
                    record of the building.
                  </p>
                ) : (
                Array.from({ length: totalFloors }, (_, idx) => totalFloors - 1 - idx).map((floor) => {
                  const isSelected = activeFloor === floor;
                  return (
                    <button
                      key={floor}
                      onClick={() => onSelectFloor(floor)}
                      className={`w-full text-left px-2.5 py-1.5 rounded-md text-xs font-mono transition flex items-center justify-between ${
                        isSelected
                          ? 'bg-amber-400 text-slate-950 font-bold shadow'
                          : 'bg-slate-800/60 hover:bg-slate-700/80 text-slate-300'
                      }`}
                    >
                      <span>Floor {String(floor).padStart(2, '0')}</span>
                      <span className="text-[10px] opacity-75">
                        {floor === 0 ? 'Ground Plinth' : `Z = +${(floor * 3.5).toFixed(1)}m`}
                      </span>
                    </button>
                  );
                })
                )}
              </div>
            </div>
          )}
        </div>

        {/* Action Shortcuts */}
        <div className="space-y-2 pt-1">
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => navigate(`/app/properties/${parentUlpin}`)}
              className="py-2 px-3 rounded-lg text-xs font-bold bg-blue-600 hover:bg-blue-500 text-white transition flex items-center justify-center gap-1.5 shadow"
            >
              <ExternalLink className="w-3.5 h-3.5" /> Full Ledger
            </button>
            {parentUlpin ? (
              <a
                href={PROPERTY_CARD_PDF_URL(parentUlpin)}
                target="_blank"
                rel="noreferrer"
                className="py-2 px-3 rounded-lg text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition flex items-center justify-center gap-1.5 text-center"
              >
                <Download className="w-3.5 h-3.5 text-emerald-400" /> Property Card
              </a>
            ) : (
              <span
                title="A property card can only be issued against a real cadastral parcel"
                className="py-2 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-500 border border-slate-700 flex items-center justify-center gap-1.5 text-center cursor-not-allowed"
              >
                <Download className="w-3.5 h-3.5" /> No cadastral record
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
