import { tint } from './tint';
import React, { useState } from 'react';
import {
  Box,
  Eye,
  Sliders,
} from 'lucide-react';

interface Props {
  theme: 'brutalist' | 'swiss' | 'kinetic' | 'neo' | 'botanical';
  isLightMode?: boolean;
}

export const CadastralWireframeInspector: React.FC<Props> = ({ theme, isLightMode = false }) => {
  const [viewMode, setViewMode] = useState<'ISOMETRIC' | 'SECTION_CUT' | 'PARCEL_PLAN'>('ISOMETRIC');
  const [activeLayer, setActiveLayer] = useState<{
    structure: boolean;
    strata: boolean;
    mep: boolean;
    boundary: boolean;
    dimensions: boolean;
  }>({
    structure: true,
    strata: true,
    mep: true,
    boundary: true,
    dimensions: true,
  });
  const [inspectedElement, setInspectedElement] = useState<string | null>('SLAB_L4');

  const isBrutalistLight = theme === 'brutalist' && isLightMode;

  // neutral-400 is the dark-theme caption grey and only reaches 2.5:1 on

  // paper, so the light variant needs a darker step of the same ramp.

  const mutedText = isBrutalistLight ? 'text-neutral-600' : 'text-neutral-400';

  const midText = isBrutalistLight ? 'text-neutral-600' : 'text-neutral-400';

  const okText = isBrutalistLight ? 'text-emerald-700' : 'text-emerald-400';
  const isSwiss = theme === 'swiss';
  const isKinetic = theme === 'kinetic';
  const isNeo = theme === 'neo';
  const isBotanical = theme === 'botanical';

  const cardBorder = isSwiss
    ? 'border border-neutral-300 bg-white text-neutral-900'
    : isKinetic
    ? 'border-2 border-[#3F3F46] bg-[#09090B] text-white'
    : isNeo
    ? 'border-4 border-black bg-white text-black shadow-[6px_6px_0px_0px_#000]'
    : isBotanical
    ? 'border border-[#E6E2DA] bg-white/95 rounded-3xl text-[#2D3A31] shadow-[0_15px_30px_-10px_rgba(45,58,49,0.06)]'
    : isBrutalistLight
    ? 'border-2 border-black bg-white text-black shadow-[4px_4px_0px_0px_#000]'
    : 'border border-white/20 bg-[#090B0E] text-white shadow-2xl';

  const accentColor = isSwiss
    ? '#FF3000'
    : isKinetic
    ? '#DFE104'
    : isNeo
    ? '#FF6B6B'
    : isBotanical
    ? '#2D3A31'
    : isBrutalistLight
    ? '#000000'
    : '#00FF66';

  const toggleLayer = (layerKey: keyof typeof activeLayer) => {
    setActiveLayer((prev) => ({ ...prev, [layerKey]: !prev[layerKey] }));
  };

  return (
    <section className="py-16 px-6 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b pb-6 border-neutral-300">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 text-[11px] font-mono uppercase tracking-widest bg-neutral-100 border border-neutral-300 text-neutral-900">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: accentColor }} />
            ARCHITECTURAL BLUEPRINT & WIREFRAME SCHEMATIC
          </div>
          <h2 className="text-3xl sm:text-4xl font-black uppercase tracking-tight">
            INTERACTIVE SPATIAL BLUEPRINTS
          </h2>
          <p className={`text-sm font-mono ${midText} max-w-2xl`}>
            Switch between isometric 3D wireframe projections, cross-sectional architectural transverse cuts, and geodetic cadastral boundary polygons.
          </p>
        </div>

        {/* View Mode Switcher */}
        <div className="flex items-center gap-1.5 p-1 bg-neutral-200/50 rounded-xl font-mono text-xs">
          <button
            onClick={() => setViewMode('ISOMETRIC')}
            className={`px-3 py-1.5 rounded-lg transition ${
              viewMode === 'ISOMETRIC'
                ? 'bg-black text-white font-bold'
                : isBrutalistLight ? 'text-neutral-600 hover:text-black' : 'text-neutral-300 hover:text-white'
            }`}
          >
            Isometric Wireframe
          </button>
          <button
            onClick={() => setViewMode('SECTION_CUT')}
            className={`px-3 py-1.5 rounded-lg transition ${
              viewMode === 'SECTION_CUT'
                ? 'bg-black text-white font-bold'
                : isBrutalistLight ? 'text-neutral-600 hover:text-black' : 'text-neutral-300 hover:text-white'
            }`}
          >
            Elevation Section (A-A')
          </button>
          <button
            onClick={() => setViewMode('PARCEL_PLAN')}
            className={`px-3 py-1.5 rounded-lg transition ${
              viewMode === 'PARCEL_PLAN'
                ? 'bg-black text-white font-bold'
                : isBrutalistLight ? 'text-neutral-600 hover:text-black' : 'text-neutral-300 hover:text-white'
            }`}
          >
            Parcel Boundary (CTS 142/A)
          </button>
        </div>
      </div>

      {/* Main Inspector Canvas & Layer Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Wireframe Canvas Area */}
        <div className={`lg:col-span-8 p-6 ${cardBorder} relative overflow-hidden`}>
          {/* Top HUD Controls */}
          <div className="flex items-center justify-between border-b pb-4 mb-4 border-neutral-200 text-xs font-mono">
            <div className="flex items-center gap-3">
              <span className="font-bold uppercase tracking-wider">
                CTS 142/A · AIROLI SECTOR 8 · CADASTRAL SCALE 1:200
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className={`text-[11px] ${mutedText}`}>VECTOR RENDERING ACTIVE</span>
            </div>
          </div>

          {/* Interactive SVG Wireframe Graphic */}
          <div className="relative w-full h-[440px] bg-neutral-950 border border-neutral-800 rounded-lg flex items-center justify-center overflow-hidden group select-none">
            {/* Background Engineering Coordinate Grid */}
            <svg
              className="absolute inset-0 w-full h-full opacity-20 pointer-events-none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <defs>
                <pattern id="wireframeGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#00ff66" strokeWidth="0.5" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#wireframeGrid)" />
            </svg>

            {/* VIEW 1: ISOMETRIC WIREFRAME PROJECTION */}
            {viewMode === 'ISOMETRIC' && (
              <svg viewBox="0 0 800 500" className="w-full h-full z-10 transition-all duration-300">
                {/* Ground Plane Boundary Envelope */}
                {activeLayer.boundary && (
                  <g className="opacity-70">
                    <polygon
                      points="120,380 480,440 680,310 320,250"
                      fill="none"
                      stroke="#06b6d4"
                      strokeWidth="1.5"
                      strokeDasharray="4,4"
                    />
                    <text x="130" y="400" fill="#06b6d4" fontSize="10" fontFamily="monospace">
                      PARCEL BOUNDARY CTS 142/A (1,000.0 m²)
                    </text>
                  </g>
                )}

                {/* Subterranean Piles */}
                {activeLayer.mep && (
                  <g className="opacity-40">
                    <line x1="260" y1="360" x2="260" y2="440" stroke="#3b82f6" strokeWidth="2" strokeDasharray="2,2" />
                    <line x1="380" y1="380" x2="380" y2="460" stroke="#3b82f6" strokeWidth="2" strokeDasharray="2,2" />
                    <line x1="490" y1="340" x2="490" y2="420" stroke="#3b82f6" strokeWidth="2" strokeDasharray="2,2" />
                    <text x="270" y="450" fill="#3b82f6" fontSize="9" fontFamily="monospace">
                      16x END-BEARING PILES (-8.2M BEDROCK)
                    </text>
                  </g>
                )}

                {/* Building Footprint (Ground Plinth) */}
                {activeLayer.structure && (
                  <polygon
                    points="220,350 460,390 580,310 340,270"
                    fill="rgba(0, 255, 102, 0.05)"
                    stroke="#00ff66"
                    strokeWidth="1.5"
                    className="cursor-pointer hover:fill-emerald-500/20"
                    onClick={() => setInspectedElement('PLINTH_GR')}
                  />
                )}

                {/* Vertical Structural Columns */}
                {activeLayer.structure && (
                  <g stroke="#00ff66" strokeWidth="1" opacity="0.6">
                    <line x1="220" y1="350" x2="220" y2="150" />
                    <line x1="460" y1="390" x2="460" y2="190" />
                    <line x1="580" y1="310" x2="580" y2="110" />
                    <line x1="340" y1="270" x2="340" y2="070" />
                  </g>
                )}

                {/* Floor Slabs Stack */}
                {activeLayer.strata && (
                  <>
                    {/* Level 1 */}
                    <polygon
                      points="220,310 460,350 580,270 340,230"
                      fill="rgba(0, 255, 102, 0.08)"
                      stroke="#00ff66"
                      strokeWidth="1"
                      className="cursor-pointer hover:stroke-white hover:fill-white/10"
                      onClick={() => setInspectedElement('SLAB_L1')}
                    />
                    {/* Level 2 */}
                    <polygon
                      points="220,270 460,310 580,230 340,190"
                      fill="rgba(0, 255, 102, 0.08)"
                      stroke="#00ff66"
                      strokeWidth="1"
                      className="cursor-pointer hover:stroke-white hover:fill-white/10"
                      onClick={() => setInspectedElement('SLAB_L2')}
                    />
                    {/* Level 3 */}
                    <polygon
                      points="220,230 460,270 580,190 340,150"
                      fill="rgba(0, 255, 102, 0.08)"
                      stroke="#00ff66"
                      strokeWidth="1"
                      className="cursor-pointer hover:stroke-white hover:fill-white/10"
                      onClick={() => setInspectedElement('SLAB_L3')}
                    />
                    {/* Level 4 */}
                    <polygon
                      points="220,190 460,230 580,150 340,110"
                      fill="rgba(0, 255, 102, 0.15)"
                      stroke={inspectedElement === 'SLAB_L4' ? '#ffffff' : '#00ff66'}
                      strokeWidth={inspectedElement === 'SLAB_L4' ? '2.5' : '1'}
                      className="cursor-pointer hover:stroke-white hover:fill-white/20"
                      onClick={() => setInspectedElement('SLAB_L4')}
                    />
                    {/* Rooftop Air-Rights Prism */}
                    <polygon
                      points="220,150 460,190 580,110 340,070"
                      fill="rgba(220, 38, 38, 0.1)"
                      stroke="#dc2626"
                      strokeWidth="1.5"
                      strokeDasharray="3,3"
                      className="cursor-pointer hover:fill-red-500/20"
                      onClick={() => setInspectedElement('ROOF_AIR_RIGHTS')}
                    />
                  </>
                )}

                {/* Dimension Callouts */}
                {activeLayer.dimensions && (
                  <g fill="#ffffff" fontSize="9" fontFamily="monospace">
                    <line x1="190" y1="350" x2="190" y2="150" stroke="#ffffff" strokeWidth="0.75" />
                    <text x="140" y="255" fill="#00ff66">H: 18.00m</text>
                    <line x1="220" y1="410" x2="460" y2="450" stroke="#ffffff" strokeWidth="0.75" />
                    <text x="320" y="445" fill="#ffffff">W: 30.00m</text>
                    <line x1="480" y1="440" x2="600" y2="360" stroke="#ffffff" strokeWidth="0.75" />
                    <text x="560" y="410" fill="#ffffff">D: 17.00m</text>
                  </g>
                )}
              </svg>
            )}

            {/* VIEW 2: ELEVATION SECTION CUT (A-A') */}
            {viewMode === 'SECTION_CUT' && (
              <svg viewBox="0 0 800 500" className="w-full h-full z-10">
                {/* Ground Line */}
                <line x1="60" y1="340" x2="740" y2="340" stroke="#8B7355" strokeWidth="3" />
                <text x="80" y="330" fill="#8B7355" fontSize="10" fontFamily="monospace">
                  NATURAL GROUND LEVEL ±0.00M (DATUM)
                </text>

                {/* Subterranean Basement B1 */}
                <rect
                  x="200"
                  y="340"
                  width="400"
                  height="70"
                  fill="rgba(59, 130, 246, 0.1)"
                  stroke="#3b82f6"
                  strokeWidth="2"
                  className="cursor-pointer hover:fill-blue-500/20"
                  onClick={() => setInspectedElement('BASEMENT_B1')}
                />
                <text x="330" y="380" fill="#3b82f6" fontSize="11" fontFamily="monospace">
                  BASEMENT B1 (-3.50M) · 24 PARKING STALLS
                </text>

                {/* Ground Plinth */}
                <rect
                  x="200"
                  y="280"
                  width="400"
                  height="60"
                  fill="rgba(0, 255, 102, 0.05)"
                  stroke="#00ff66"
                  strokeWidth="1.5"
                  className="cursor-pointer"
                  onClick={() => setInspectedElement('PLINTH_GR')}
                />
                <text x="320" y="315" fill="#00ff66" fontSize="11" fontFamily="monospace">
                  GROUND FLOOR (+0.60M TO +3.60M)
                </text>

                {/* Upper Floors L1, L2, L3, L4 */}
                {[
                  { y: 220, label: 'LEVEL 01 (+3.60M TO +7.20M)', id: 'SLAB_L1' },
                  { y: 160, label: 'LEVEL 02 (+7.20M TO +10.80M)', id: 'SLAB_L2' },
                  { y: 100, label: 'LEVEL 03 (+10.80M TO +14.40M)', id: 'SLAB_L3' },
                  { y: 40, label: 'LEVEL 04 (+14.40M TO +18.00M)', id: 'SLAB_L4' },
                ].map((fl) => (
                  <g key={fl.id}>
                    <rect
                      x="200"
                      y={fl.y}
                      width="400"
                      height="60"
                      fill="rgba(0, 255, 102, 0.08)"
                      stroke="#00ff66"
                      strokeWidth="1.5"
                      className="cursor-pointer hover:fill-emerald-500/20"
                      onClick={() => setInspectedElement(fl.id)}
                    />
                    <text x="320" y={fl.y + 35} fill="#00ff66" fontSize="11" fontFamily="monospace">
                      {fl.label}
                    </text>
                  </g>
                ))}

                {/* Rooftop Parapet */}
                <rect x="200" y="25" width="400" height="15" fill="none" stroke="#dc2626" strokeWidth="1.5" />
                <text x="340" y="36" fill="#dc2626" fontSize="9" fontFamily="monospace">
                  PARAPET WALL (+19.20M)
                </text>

                {/* Setback Dimensions Left and Right */}
                <line x1="80" y1="280" x2="200" y2="280" stroke="#06b6d4" strokeWidth="1" strokeDasharray="3,3" />
                <text x="100" y="270" fill="#06b6d4" fontSize="10" fontFamily="monospace">
                  NORTH SETBACK: 4.82M
                </text>

                <line x1="600" y1="280" x2="720" y2="280" stroke="#06b6d4" strokeWidth="1" strokeDasharray="3,3" />
                <text x="610" y="270" fill="#06b6d4" fontSize="10" fontFamily="monospace">
                  SOUTH SETBACK: 3.15M
                </text>
              </svg>
            )}

            {/* VIEW 3: CADASTRAL PARCEL TOPOLOGY (CTS 142/A PLAN) */}
            {viewMode === 'PARCEL_PLAN' && (
              <svg viewBox="0 0 800 500" className="w-full h-full z-10">
                {/* Parcel Boundary Polygon */}
                <polygon
                  points="180,100 620,100 620,400 180,400"
                  fill="rgba(6, 182, 212, 0.05)"
                  stroke="#06b6d4"
                  strokeWidth="2"
                />
                <text x="190" y="125" fill="#06b6d4" fontSize="12" fontFamily="monospace" fontWeight="bold">
                  CTS 142/A (PLOT AREA: 1,000.00 M²)
                </text>

                {/* Building Footprint */}
                <rect
                  x="280"
                  y="180"
                  width="260"
                  height="170"
                  fill="rgba(0, 255, 102, 0.15)"
                  stroke="#00ff66"
                  strokeWidth="2"
                  className="cursor-pointer"
                  onClick={() => setInspectedElement('FOOTPRINT_2D')}
                />
                <text x="310" y="270" fill="#00ff66" fontSize="11" fontFamily="monospace" fontWeight="bold">
                  PLINTH FOOTPRINT: 510.0 M²
                </text>

                {/* Boundary Bearings and Distances */}
                <text x="360" y="90" fill="#ffffff" fontSize="10" fontFamily="monospace">
                  N 89° 14' E · 40.00 m
                </text>
                <text x="635" y="250" fill="#ffffff" fontSize="10" fontFamily="monospace">
                  S 00° 46' E · 25.00 m
                </text>
                <text x="360" y="420" fill="#ffffff" fontSize="10" fontFamily="monospace">
                  S 89° 14' W · 40.00 m
                </text>
                <text x="80" y="250" fill="#ffffff" fontSize="10" fontFamily="monospace">
                  N 00° 46' W · 25.00 m
                </text>

                {/* Adjoining Plot Labels */}
                <text x="360" y="40" fill="#666666" fontSize="11" fontFamily="monospace">
                  [NORTH] 18.0M SECTOR ROAD
                </text>
                <text x="640" y="150" fill="#666666" fontSize="10" fontFamily="monospace">
                  [EAST] CTS 143
                </text>
                <text x="360" y="470" fill="#666666" fontSize="10" fontFamily="monospace">
                  [SOUTH] CTS 150 GREEN BELT
                </text>
                <text x="80" y="150" fill="#666666" fontSize="10" fontFamily="monospace">
                  [WEST] CTS 141
                </text>
              </svg>
            )}

            {/* Click to inspect watermark. The pill stays dark in both themes, so the
                label must too - it cannot follow the surface theme token. */}
            <div className="absolute bottom-3 left-3 text-[10px] font-mono text-neutral-300 bg-black/60 px-2 py-1 rounded pointer-events-none">
              TIP: Click any structural element or floor slab to inspect technical specs.
            </div>
          </div>
        </div>

        {/* Right Side: Layer Visibility Controls & Inspected Element Telemetry */}
        <div className="lg:col-span-4 space-y-6">
          {/* Layer Visibility Toggles */}
          <div className={`p-5 ${cardBorder} space-y-4`}>
            <div className="flex items-center justify-between border-b pb-3 border-neutral-200">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4" style={{ color: accentColor }} />
                <span className="font-mono font-bold text-xs uppercase">Schematic Layers</span>
              </div>
              <span className={`text-[10px] font-mono ${mutedText}`}>TOGGLE VISIBILITY</span>
            </div>

            <div className="space-y-2 text-xs font-mono">
              {[
                { key: 'structure', label: 'RC Superstructure & Columns', color: '#00ff66' },
                { key: 'strata', label: 'Volumetric Floor Envelopes', color: '#10b981' },
                { key: 'mep', label: 'Subterranean Foundation & Piles', color: '#3b82f6' },
                { key: 'boundary', label: 'Cadastral Boundary CTS 142/A', color: '#06b6d4' },
                { key: 'dimensions', label: 'Setback & Height Dimensions', color: '#f59e0b' },
              ].map((layer) => {
                const isEnabled = activeLayer[layer.key as keyof typeof activeLayer];

                return (
                  <button
                    key={layer.key}
                    onClick={() => toggleLayer(layer.key as keyof typeof activeLayer)}
                    className={`w-full flex items-center justify-between p-2.5 rounded border transition text-left ${
                      isEnabled
                        ? 'border-neutral-300 bg-neutral-100/70 text-black dark:bg-neutral-800 dark:text-white'
                        : `border-transparent ${mutedText} hover:bg-neutral-100/40 opacity-50`
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: isEnabled ? layer.color : '#666666' }}
                      />
                      <span>{layer.label}</span>
                    </div>
                    <Eye className={`w-3.5 h-3.5 ${isEnabled ? 'text-black dark:text-white' : mutedText}`} />
                  </button>
                );
              })}
            </div>
          </div>

          {/* Inspected Element Telemetry Box */}
          <div className={`p-5 ${cardBorder} space-y-4`}>
            <div className="flex items-center justify-between border-b pb-3 border-neutral-200">
              <div className="flex items-center gap-2">
                <Box className="w-4 h-4" style={{ color: accentColor }} />
                <span className="font-mono font-bold text-xs uppercase">Selected Component</span>
              </div>
              <span className={`text-[10px] font-mono text-emerald-800 font-bold bg-emerald-50 px-2 py-0.5 rounded`}>
                VERIFIED
              </span>
            </div>

            <div className="space-y-3 font-mono text-xs">
              <div className="p-3 bg-neutral-100 dark:bg-neutral-800/40 border border-neutral-200 rounded">
                <div className={`text-[10px] ${mutedText} uppercase`}>Component Code</div>
                <div className="text-sm font-black text-black dark:text-white mt-0.5">
                  {inspectedElement || 'SLAB_L4'}
                </div>
                <div className={`text-[11px] ${midText} mt-1`}>
                  Reinforced Concrete Diaphragm · Grade M35 Seismic Spec
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2 border border-neutral-200 bg-neutral-50/50">
                  <div className={`text-[9px] ${mutedText} uppercase`}>Elevation Datum</div>
                  <div className="font-bold text-black dark:text-white mt-0.5">+14.40m to +18.00m</div>
                </div>
                <div className="p-2 border border-neutral-200 bg-neutral-50/50">
                  <div className={`text-[9px] ${mutedText} uppercase`}>Carpet Area</div>
                  <div className="font-bold text-black dark:text-white mt-0.5">420.00 m²</div>
                </div>
                <div className="p-2 border border-neutral-200 bg-neutral-50/50">
                  <div className={`text-[9px] ${mutedText} uppercase`}>Built-Up Volume</div>
                  <div className="font-bold text-black dark:text-white mt-0.5">1,785.00 m³</div>
                </div>
                <div className="p-2 border border-neutral-200 bg-neutral-50/50">
                  <div className={`text-[9px] ${mutedText} uppercase`}>Encroachment</div>
                  <div className={`font-bold ${tint(isBrutalistLight,'emerald')} mt-0.5`}>0.00 mm (Pass)</div>
                </div>
              </div>

              <div className={`pt-2 border-t border-neutral-200 text-[10px] ${mutedText} space-y-1`}>
                <div>Merkle Leaf: <span className="font-bold text-black dark:text-white">0x8f2a...991c</span></div>
                <div>Sanction Ref: <span className="font-bold text-black dark:text-white">CIDCO/BP-2018/891</span></div>
                <div>Luhn Checksum: <span className={`${okText} font-bold`}>MATCH (Mod 36)</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
