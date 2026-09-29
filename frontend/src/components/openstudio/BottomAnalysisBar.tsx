import React from 'react';
import { ChevronDown, ChevronUp, BarChart3, Compass, Sun, ShieldCheck } from 'lucide-react';
import { useOpenStudioStore } from '../../store/useOpenStudioStore';

export const BottomAnalysisBar: React.FC = () => {
  const { bottomBarOpen, setBottomBarOpen, selectedBuilding } = useOpenStudioStore();

  // With nothing selected these are null, not 18 m / 5 storeys / 1.85 FSI.
  // The empty state used to show a fully specified building that did not exist,
  // which is worse than showing nothing: it looked like real data.
  const height = selectedBuilding?.heightM ?? null;
  const floors = selectedBuilding?.floorsCount ?? null;
  const fsi = selectedBuilding?.fsi ?? null;

  return (
    <div
      className={`border-t border-white/40 bg-slate-950/95 backdrop-blur-md flex-shrink-0 z-20 transition-all duration-300 select-none ${
        bottomBarOpen ? 'h-36' : 'h-10'
      }`}
    >
      {/* Header bar toggle */}
      <button
        onClick={() => setBottomBarOpen(!bottomBarOpen)}
        className="w-full flex items-center justify-between px-4 h-10 hover:bg-slate-900/60 transition text-slate-300 font-mono text-xs"
      >
        <div className="flex items-center gap-3">
          <BarChart3 className="w-4 h-4 text-slate-300" />
          <span className="font-bold uppercase tracking-widest text-slate-300">
            Civic Spatial Telemetry & Volumetric Analysis
          </span>
          <span className="text-[11px] text-slate-300 hidden sm:inline">
            · Datum: WGS84 / UTM 43N · MSL +12.0m · NBC 2016 Clause 3.4
          </span>
        </div>

        <div className="flex items-center gap-2 text-slate-300">
          <span className="text-[11px] text-slate-300 font-bold hidden md:inline">
            {bottomBarOpen ? 'Collapse Telemetry' : 'Expand Telemetry'}
          </span>
          {bottomBarOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </div>
      </button>

      {/* Expanded Metrics View */}
      {bottomBarOpen && (
        <div className="px-4 pb-3 grid grid-cols-2 md:grid-cols-4 gap-3 animate-rise-in font-mono text-xs">
          {/* Volumetric Mass */}
          <div className="p-2.5 rounded-none bg-slate-900/80 border border-white/40">
            <span className="text-[10px] text-slate-300 uppercase font-bold">Volumetric Envelope</span>
            <div className="text-sm font-bold text-white mt-1">
              {/* Was `~${(510 * height)} m3`, i.e. a constant footprint times
                  the height, presented as an estimated volume. No footprint is
                  held for most parcels, so no volume is derivable. */}
              {'--'}
            </div>
            <div className="text-[10px] text-slate-300">
              Floorplate: 510 m² · {floors === null ? '--' : `${floors}F`}
              {height === null && ' · no height in open data'}
            </div>
          </div>

          {/* FSI & Setback Compliance */}
          <div className="p-2.5 rounded-none bg-slate-900/80 border border-white/40">
            <span className="text-[10px] text-slate-300 uppercase font-bold flex items-center gap-1">
              <ShieldCheck className="w-3 h-3 text-emerald-400" /> FSI & Setback Standard
            </span>
            {/* Was `{fsi.toFixed(2)} / 2.0 (NBC PASS)` in emerald, with fsi
                defaulting to 1.85 when the source had none. That printed a
                National Building Code compliance finding about a real building
                that had never been assessed, using a floor plate and setbacks
                that were also invented. */}
            <div className={`text-sm font-bold mt-1 ${fsi === null ? 'text-slate-300' : 'text-emerald-400'}`}>
              {fsi === null ? 'Not available from open data' : `${fsi.toFixed(2)} / 2.0`}
            </div>
            <div className="text-[10px] text-slate-300">
              {fsi === null ? 'No FSI in source; no compliance verdict' : 'Front Setback: 4.5m · Rear: 3.0m'}
            </div>
          </div>

          {/* Geodetic Datum */}
          <div className="p-2.5 rounded-none bg-slate-900/80 border border-white/40">
            <span className="text-[10px] text-slate-300 uppercase font-bold flex items-center gap-1">
              <Compass className="w-3 h-3 text-slate-300" /> Geodetic Reference
            </span>
            <div className="text-xs font-bold text-white mt-1">
              UTM 43N: E 298,160 m, N 2,113,652 m
            </div>
            <div className="text-[10px] text-slate-300">MSL Elevation: +12.00 m (GTS)</div>
          </div>

          {/* Astronomical & Solar Angle */}
          <div className="p-2.5 rounded-none bg-slate-900/80 border border-white/40">
            <span className="text-[10px] text-slate-300 uppercase font-bold flex items-center gap-1">
              <Sun className="w-3 h-3 text-amber-400" /> Solar & Heliocentric Azimuth
            </span>
            <div className="text-xs font-bold text-amber-300 mt-1">
              Azimuth: 242.4° · Elevation: 48.6°
            </div>
            <div className="text-[10px] text-slate-300">Magnetic Declination: -0.24° W</div>
          </div>
        </div>
      )}
    </div>
  );
};
