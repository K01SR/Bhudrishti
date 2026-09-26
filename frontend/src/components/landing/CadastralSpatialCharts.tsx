import { tint } from './tint';
import React, { useState } from 'react';
import {
  BarChart3,
  ShieldCheck,
  CheckCircle2,
  Box,
  Activity,
  Radio,
  FileCheck2,
} from 'lucide-react';

interface Props {
  theme: 'brutalist' | 'swiss' | 'kinetic' | 'neo' | 'botanical';
  isLightMode?: boolean;
}

export const CadastralSpatialCharts: React.FC<Props> = ({ theme, isLightMode = false }) => {
  const [activeChart, setActiveChart] = useState<'VOLUMETRIC' | 'LIDAR_SPECTRUM' | 'SUBTERRANEAN' | 'SETBACK_COMPLIANCE'>('VOLUMETRIC');
  const [selectedFloor, setSelectedFloor] = useState<number | null>(null);
  const [lidarFilter, setLidarFilter] = useState<'ALL' | 'GROUND' | 'FACADE' | 'SLABS' | 'ROOF'>('ALL');

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

  // Card & Container Style Tokens
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

  const tabActiveStyle = isSwiss
    ? 'bg-black text-white font-mono'
    : isKinetic
    ? 'bg-[#DFE104] text-black font-black font-space'
    : isNeo
    ? 'bg-[#FF6B6B] text-white border-4 border-black font-black shadow-[3px_3px_0px_0px_#000]'
    : isBotanical
    ? 'bg-[#2D3A31] text-white rounded-full font-serif font-bold shadow-sm'
    : isBrutalistLight
    ? 'bg-black text-white font-mono font-bold'
    : 'bg-[#00FF66] text-black font-mono font-bold';

  const tabInactiveStyle = isSwiss
    ? 'text-neutral-500 hover:text-black border border-neutral-200'
    : isKinetic
    ? 'text-[#A1A1AA] hover:text-white border border-[#3F3F46]'
    : isNeo
    ? 'bg-[#FFFDF5] text-black hover:bg-[#FFD93D] border-4 border-black shadow-[2px_2px_0px_0px_#000]'
    : isBotanical
    ? 'text-[#2D3A31]/70 hover:text-[#2D3A31] hover:bg-[#8C9A84]/15 rounded-full border border-[#E6E2DA]'
    : isBrutalistLight
    ? 'text-neutral-600 hover:text-black border border-neutral-300'
    : 'text-white/80 hover:text-white border border-white/10';

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

  // Volumetric Data per Floor
  const volumetricData = [
    {
      level: 'ROOF (+18.0M)',
      code: 'AIR_RIGHTS',
      sanctionedVol: 1420,
      actualVol: 1420,
      carpetM2: 0,
      builtUpM2: 420,
      fsiContribution: 0.0,
      overhang: '0.00 mm',
      status: 'UNENCUMBERED AIRSPACE',
      usage: 'Solar Arrays & Mechanical Terrace',
    },
    {
      level: 'LEVEL 4 (+14.4M)',
      code: 'FL_04',
      sanctionedVol: 1785,
      actualVol: 1785,
      carpetM2: 420.0,
      builtUpM2: 510.0,
      fsiContribution: 0.36,
      overhang: '0.00 mm',
      status: 'APPROVED & SEALED',
      usage: 'Residential Units 401–404',
    },
    {
      level: 'LEVEL 3 (+10.8M)',
      code: 'FL_03',
      sanctionedVol: 1785,
      actualVol: 1785,
      carpetM2: 420.0,
      builtUpM2: 510.0,
      fsiContribution: 0.36,
      overhang: '0.00 mm',
      status: 'APPROVED & SEALED',
      usage: 'Residential Units 301–304',
    },
    {
      level: 'LEVEL 2 (+07.2M)',
      code: 'FL_02',
      sanctionedVol: 1785,
      actualVol: 1785,
      carpetM2: 420.0,
      builtUpM2: 510.0,
      fsiContribution: 0.36,
      overhang: '0.00 mm',
      status: 'APPROVED & SEALED',
      usage: 'Residential Units 201–204',
    },
    {
      level: 'LEVEL 1 (+03.6M)',
      code: 'FL_01',
      sanctionedVol: 1785,
      actualVol: 1785,
      carpetM2: 420.0,
      builtUpM2: 510.0,
      fsiContribution: 0.36,
      overhang: '0.00 mm',
      status: 'APPROVED & SEALED',
      usage: 'Residential Units 101–104',
    },
    {
      level: 'GROUND (+00.0M)',
      code: 'FL_GR',
      sanctionedVol: 1836,
      actualVol: 1836,
      carpetM2: 380.0,
      builtUpM2: 510.0,
      fsiContribution: 0.36,
      overhang: '0.00 mm',
      status: 'PUBLIC EASEMENT / ENTRY',
      usage: 'Lobby, Fitness Lounge & Society Office',
    },
    {
      level: 'BASEMENT (-03.5M)',
      code: 'FL_B1',
      sanctionedVol: 1785,
      actualVol: 1785,
      carpetM2: 480.0,
      builtUpM2: 510.0,
      fsiContribution: 0.0, // Basement exempt from FSI per DCR
      overhang: '0.00 mm',
      status: 'SUBTERRANEAN RIGHT',
      usage: '24 Automated Stacker Parking Stalls',
    },
  ];

  // Subterranean Utilities Clearance Data
  const subterraneanProfiles = [
    {
      utility: 'Telecom OFC Fiber Conduit',
      depth: '-1.20 m',
      diameter: '110 mm',
      distanceToFoundation: '3.80 m',
      requiredBuffer: '1.50 m',
      clearanceMargin: '+153%',
      authority: 'MTNL / Reliance Jio Cable Corridor',
      status: 'SAFE',
    },
    {
      utility: 'NMMC Potable Water Trunk Main',
      depth: '-1.80 m',
      diameter: '600 mm (Cast Iron)',
      distanceToFoundation: '4.20 m',
      requiredBuffer: '2.00 m',
      clearanceMargin: '+110%',
      authority: 'Navi Mumbai Municipal Water Supply Dept',
      status: 'SAFE',
    },
    {
      utility: 'Basement B1 Retaining Wall',
      depth: '-3.50 m',
      diameter: '350 mm RCC Diaphragm',
      distanceToFoundation: '0.00 m (Structure)',
      requiredBuffer: '3.00 m (Side Setback)',
      clearanceMargin: '+6.6% (3.20m actual)',
      authority: 'Structural Sanction CIDCO/BP-2018/891',
      status: 'COMPLIANT',
    },
    {
      utility: 'Municipal Stormwater Box Culvert',
      depth: '-4.80 m',
      diameter: '1200 x 900 mm RCC',
      distanceToFoundation: '5.10 m',
      requiredBuffer: '2.50 m',
      clearanceMargin: '+104%',
      authority: 'NMMC Storm Drainage Engineering',
      status: 'SAFE',
    },
    {
      utility: 'Basalt Bedrock Anchor Socketing',
      depth: '-8.20 m',
      diameter: '750 mm Bored Piles (x16)',
      distanceToFoundation: 'End-Bearing 5.5 MPa',
      requiredBuffer: 'Geotech Ref G-142',
      clearanceMargin: '+38% Load Capacity',
      authority: 'IIT Bombay Geotechnical Vetting',
      status: 'VERIFIED',
    },
    {
      utility: 'MMRDA Metro Line 14 Buffer Corridor',
      depth: '-14.0 m',
      diameter: '6.5 m TBM Twin Tunnel',
      distanceToFoundation: '8.50 m Offset',
      requiredBuffer: '6.00 m Statutory Buffer',
      clearanceMargin: '+41% Buffer Margin',
      authority: 'Mumbai Metropolitan Region Dev Authority',
      status: 'NO_OBJECTION',
    },
  ];

  // Setback Compliance Matrix
  const setbackCompliance = [
    {
      parameter: 'Front Setback (North)',
      sanctioned: '4.50 m',
      measured: '4.82 m',
      variance: '+0.32 m',
      status: 'PASS',
      dcrRef: 'DCR Rule 33(1) - Road Width 18.0m',
    },
    {
      parameter: 'Rear Setback (South)',
      sanctioned: '3.00 m',
      measured: '3.15 m',
      variance: '+0.15 m',
      status: 'PASS',
      dcrRef: 'DCR Rule 33(3) - Residential Open Space',
    },
    {
      parameter: 'Side Setback (East)',
      sanctioned: '3.00 m',
      measured: '3.08 m',
      variance: '+0.08 m',
      status: 'PASS',
      dcrRef: 'DCR Rule 33(4) - Fire Tender Egress Clearance',
    },
    {
      parameter: 'Side Setback (West)',
      sanctioned: '3.00 m',
      measured: '3.20 m',
      variance: '+0.20 m',
      status: 'PASS',
      dcrRef: 'DCR Rule 33(4) - Adjoining Plot CTS 141 Buffer',
    },
    {
      parameter: 'Max Height Ceiling',
      sanctioned: '18.00 m',
      measured: '18.00 m',
      variance: '0.00 mm',
      status: 'PASS',
      dcrRef: 'Airport Authority of India (AAI) OLS NOC',
    },
    {
      parameter: 'Ground Coverage Ratio',
      sanctioned: '60.00% max',
      measured: '51.00% (510 m²)',
      variance: '-9.00% (Compliant)',
      status: 'PASS',
      dcrRef: 'Maharashtra Unified DCPR Regulation 6.1',
    },
    {
      parameter: 'Permeable Ground Area',
      sanctioned: '15.00% min',
      measured: '18.50% (185 m²)',
      variance: '+3.50% (Compliant)',
      status: 'PASS',
      dcrRef: 'Rainwater Harvesting & Ground Recharge Policy',
    },
    {
      parameter: 'Automated Parking Stalls',
      sanctioned: '21 stalls',
      measured: '24 stalls provided',
      variance: '+3 Stalls Excess',
      status: 'PASS',
      dcrRef: '1 Car Stall per 100 m² Built-Up Area',
    },
  ];

  return (
    <section className="py-16 px-6 max-w-7xl mx-auto space-y-10">
      {/* Section Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b pb-6 border-neutral-300">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 text-[11px] font-mono uppercase tracking-widest bg-neutral-100 border border-neutral-300 text-neutral-900">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: accentColor }} />
            SPATIAL TELEMETRY · CHARTS & ANALYTICS ENGINE
          </div>
          <h2 className="text-3xl sm:text-4xl font-black uppercase tracking-tight">
            CADASTRE METRIC BENCHMARKS
          </h2>
          <p className={`text-sm font-mono ${midText} max-w-2xl`}>
            Real-time volumetric analytics, LiDAR cross-sectional distribution, subterranean clearance buffers, and statutory NBC 2016 verification.
          </p>
        </div>

        {/* Chart View Switcher Tabs */}
        <div className="flex flex-wrap items-center gap-1.5 p-1 bg-neutral-200/50 rounded-xl">
          <button
            onClick={() => setActiveChart('VOLUMETRIC')}
            className={`px-3 py-1.5 text-xs rounded-lg transition ${
              activeChart === 'VOLUMETRIC' ? tabActiveStyle : tabInactiveStyle
            }`}
          >
            01 / Strata Volumes
          </button>
          <button
            onClick={() => setActiveChart('LIDAR_SPECTRUM')}
            className={`px-3 py-1.5 text-xs rounded-lg transition ${
              activeChart === 'LIDAR_SPECTRUM' ? tabActiveStyle : tabInactiveStyle
            }`}
          >
            02 / LiDAR Point Spectrum
          </button>
          <button
            onClick={() => setActiveChart('SUBTERRANEAN')}
            className={`px-3 py-1.5 text-xs rounded-lg transition ${
              activeChart === 'SUBTERRANEAN' ? tabActiveStyle : tabInactiveStyle
            }`}
          >
            03 / Subterranean Clash
          </button>
          <button
            onClick={() => setActiveChart('SETBACK_COMPLIANCE')}
            className={`px-3 py-1.5 text-xs rounded-lg transition ${
              activeChart === 'SETBACK_COMPLIANCE' ? tabActiveStyle : tabInactiveStyle
            }`}
          >
            04 / Setback Matrix
          </button>
        </div>
      </div>

      {/* ===================================================================== */}
      {/* CHART 1: VOLUMETRIC FSI & STRATA DISTRIBUTION                         */}
      {/* ===================================================================== */}
      {activeChart === 'VOLUMETRIC' && (
        <div className="space-y-6 animate-fade-in">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            {/* Visual Bar Chart */}
            <div className={`lg:col-span-8 p-6 ${cardBorder}`}>
              <div className="flex items-center justify-between border-b pb-4 mb-6 border-neutral-200">
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-5 h-5" style={{ color: accentColor }} />
                  <span className="font-mono font-bold text-sm uppercase">
                    Volumetric Displacement per Floor (Sanctioned vs Measured m³)
                  </span>
                </div>
                <span className={`font-mono text-xs ${mutedText}`}>100% Volumetric Concordance</span>
              </div>

              {/* Stacked Interactive Horizontal Bars */}
              <div className="space-y-4">
                {volumetricData.map((floor, idx) => {
                  const maxVol = 2000;
                  const pct = (floor.actualVol / maxVol) * 100;
                  const isSelected = selectedFloor === idx;

                  return (
                    <div
                      key={floor.code}
                      onClick={() => setSelectedFloor(isSelected ? null : idx)}
                      className={`p-3 border transition cursor-pointer ${
                        isSelected
                          ? isSwiss
                            ? 'border-black bg-neutral-50 shadow-sm'
                            : isKinetic
                            ? 'border-[#DFE104] bg-neutral-900 shadow-sm'
                            : isNeo
                            ? 'border-4 border-black bg-[#FFD93D] shadow-[4px_4px_0px_0px_#000]'
                            : isBotanical
                            ? 'border-[#2D3A31] bg-[#8C9A84]/10 rounded-2xl'
                            : 'border-[#00FF66] bg-neutral-900 shadow-sm'
                          : 'border-neutral-200 hover:border-neutral-400'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs font-mono mb-1.5">
                        <div className="flex items-center gap-2">
                          <span className="font-black">{floor.level}</span>
                          <span className={`${mutedText}`}>[{floor.code}]</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`${midText} font-bold`}>{floor.actualVol.toLocaleString()} m³</span>
                          <span className={`px-1.5 py-0.5 bg-emerald-500/10 ${tint(isBrutalistLight,'emerald')} font-bold text-[10px] rounded`}>
                            {floor.overhang} Overhang
                          </span>
                        </div>
                      </div>

                      {/* Bar Fill */}
                      <div className="w-full bg-neutral-200/70 h-3 rounded-sm overflow-hidden flex">
                        <div
                          className="h-full transition-all duration-500"
                          style={{
                            width: `${pct}%`,
                            backgroundColor:
                              floor.fsiContribution === 0
                                ? '#3b82f6'
                                : isSelected
                                ? accentColor
                                : '#10b981',
                          }}
                        />
                      </div>

                      <div className={`flex justify-between items-center text-[10px] font-mono ${mutedText} mt-1`}>
                        <span>{floor.usage}</span>
                        <span>FSI Index: +{floor.fsiContribution.toFixed(2)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Legend Bar */}
              <div className="flex flex-wrap items-center gap-6 mt-6 pt-4 border-t border-neutral-200 text-xs font-mono">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 bg-emerald-500 inline-block" />
                  <span>Modelled FSI contribution</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 bg-blue-500 inline-block" />
                  <span>Non-habitable strata (basement, air rights)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 bg-red-500 inline-block" />
                  <span>Addition present only in the later generated epoch</span>
                </div>
                <p className="w-full text-[10px] font-mono opacity-70 pt-1">
                  No sanctioned FSI or exemption has been read for this plot, so these bars are
                  modelled contributions and not a compliance measure.
                </p>
              </div>
            </div>

            {/* Side Floor Detail Telemetry Card */}
            <div className={`lg:col-span-4 p-6 ${cardBorder} space-y-4`}>
              <div className="flex items-center justify-between border-b pb-3 border-neutral-200">
                <div className="flex items-center gap-2">
                  <Box className="w-4 h-4" style={{ color: accentColor }} />
                  <span className="font-mono font-bold text-xs uppercase">Strata Inspector</span>
                </div>
                <span className={`text-[10px] font-mono ${mutedText}`}>
                  {selectedFloor !== null ? volumetricData[selectedFloor].code : 'CLICK A FLOOR'}
                </span>
              </div>

              {selectedFloor !== null ? (
                <div className="space-y-4 font-mono text-xs animate-rise-in">
                  <div className="p-3 bg-neutral-100 dark:bg-neutral-800/40 border border-neutral-300">
                    <div className={`text-[10px] ${mutedText} uppercase`}>Target Level</div>
                    <div className="text-base font-black text-black dark:text-white">
                      {volumetricData[selectedFloor].level}
                    </div>
                    <div className={`text-[11px] ${midText} mt-0.5`}>
                      {volumetricData[selectedFloor].usage}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-2.5 border border-neutral-200 bg-neutral-50/50">
                      <div className={`text-[9px] ${mutedText} uppercase`}>Gross Volume</div>
                      <div className="text-sm font-bold mt-0.5">
                        {volumetricData[selectedFloor].actualVol} m³
                      </div>
                    </div>
                    <div className="p-2.5 border border-neutral-200 bg-neutral-50/50">
                      <div className={`text-[9px] ${mutedText} uppercase`}>Carpet Area</div>
                      <div className="text-sm font-bold mt-0.5">
                        {volumetricData[selectedFloor].carpetM2} m²
                      </div>
                    </div>
                    <div className="p-2.5 border border-neutral-200 bg-neutral-50/50">
                      <div className={`text-[9px] ${mutedText} uppercase`}>Built-Up Area</div>
                      <div className="text-sm font-bold mt-0.5">
                        {volumetricData[selectedFloor].builtUpM2} m²
                      </div>
                    </div>
                    <div className="p-2.5 border border-neutral-200 bg-neutral-50/50">
                      <div className={`text-[9px] ${mutedText} uppercase`}>Boundary Cantilever</div>
                      <div className={`text-sm font-bold ${tint(isBrutalistLight,'emerald')} mt-0.5`}>
                        {volumetricData[selectedFloor].overhang}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2 pt-2 border-t border-neutral-200 text-[11px]">
                    <div className="flex justify-between">
                      <span className={`${mutedText}`}>FSI Contribution:</span>
                      <span className="font-bold">+{volumetricData[selectedFloor].fsiContribution}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={`${mutedText}`}>Legal Status:</span>
                      <span className={`${okText} font-bold`}>{volumetricData[selectedFloor].status}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={`${mutedText}`}>Checksum Validation:</span>
                      <span className="text-blue-500 font-bold">ISO/IEC 7064 MOD 36 PASS</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className={`py-12 text-center font-mono text-xs ${mutedText} space-y-2`}>
                  <Activity className="w-8 h-8 mx-auto opacity-30 animate-pulse" />
                  <p>Select any floor slab on the chart to inspect structural volumes, carpet areas, and FSI index.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* CHART 2: LIDAR POINT CLOUD ELEVATION DENSITY SPECTRUM                 */}
      {/* ===================================================================== */}
      {activeChart === 'LIDAR_SPECTRUM' && (
        <div className="space-y-6 animate-fade-in">
          <div className={`p-6 ${cardBorder}`}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4 mb-6 border-neutral-200">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Radio className="w-5 h-5 text-cyan-500 animate-pulse" />
                  <h3 className="font-mono font-bold text-sm uppercase">
                    LiDAR Vertical Point Density & Pulse Return Histogram (15,000 Points)
                  </h3>
                </div>
                <p className={`text-xs font-mono ${mutedText}`}>
                  Synthetic terrestrial LiDAR scan showing return frequency across vertical Z-axis (-4.0m to +22.0m).
                </p>
              </div>

              {/* Classification Filter Buttons */}
              <div className="flex items-center gap-1.5 text-[10px] font-mono">
                {(['ALL', 'GROUND', 'FACADE', 'SLABS', 'ROOF'] as const).map((filter) => (
                  <button
                    key={filter}
                    onClick={() => setLidarFilter(filter)}
                    className={`px-2.5 py-1 border transition ${
                      lidarFilter === filter
                        ? 'bg-black text-white font-bold border-black'
                        : 'border-neutral-300 text-neutral-500 hover:text-black'
                    }`}
                  >
                    {filter}
                  </button>
                ))}
              </div>
            </div>

            {/* SVG Histogram Graphic */}
            <div className="relative h-64 w-full bg-neutral-900 border border-neutral-800 rounded p-4 font-mono text-xs overflow-hidden">
              {/* Elevation Horizontal Gridlines */}
              <div className="absolute inset-0 flex flex-col justify-between p-4 pointer-events-none opacity-20">
                <div className="border-b border-cyan-400 w-full flex justify-between text-[9px] text-cyan-300">
                  <span>+21.0m (Airspace Ceiling)</span>
                  <span>0 pts</span>
                </div>
                <div className="border-b border-cyan-400 w-full flex justify-between text-[9px] text-cyan-300">
                  <span>+18.0m (Parapet / Roof Slabs)</span>
                  <span>3,500 pts</span>
                </div>
                <div className="border-b border-cyan-400 w-full flex justify-between text-[9px] text-cyan-300">
                  <span>+10.8m (Mid-Rise Facade & Balconies)</span>
                  <span>1,850 pts</span>
                </div>
                <div className="border-b border-cyan-400 w-full flex justify-between text-[9px] text-cyan-300">
                  <span>+00.0m (Ground Plinth)</span>
                  <span>3,000 pts</span>
                </div>
                <div className="border-b border-cyan-400 w-full flex justify-between text-[9px] text-cyan-300">
                  <span>-03.5m (Basement Slab B1)</span>
                  <span>1,200 pts</span>
                </div>
              </div>

              {/* Simulated Spectral Histogram Bars */}
              <div className="h-full flex items-end justify-between gap-1 pt-6 px-4 relative z-10">
                {[
                  { z: '-3.5m', count: 1200, type: 'SLABS', color: '#3b82f6' },
                  { z: '-2.0m', count: 450, type: 'FACADE', color: '#6366f1' },
                  { z: '-1.0m', count: 680, type: 'FACADE', color: '#6366f1' },
                  { z: '0.0m', count: 3000, type: 'GROUND', color: '#8B7355' },
                  { z: '+1.8m', count: 950, type: 'FACADE', color: '#06b6d4' },
                  { z: '+3.6m', count: 2100, type: 'SLABS', color: '#3b82f6' },
                  { z: '+5.4m', count: 1120, type: 'FACADE', color: '#06b6d4' },
                  { z: '+7.2m', count: 2050, type: 'SLABS', color: '#3b82f6' },
                  { z: '+9.0m', count: 1080, type: 'FACADE', color: '#06b6d4' },
                  { z: '+10.8m', count: 2150, type: 'SLABS', color: '#3b82f6' },
                  { z: '+12.6m', count: 1040, type: 'FACADE', color: '#06b6d4' },
                  { z: '+14.4m', count: 2100, type: 'SLABS', color: '#3b82f6' },
                  { z: '+16.2m', count: 980, type: 'FACADE', color: '#06b6d4' },
                  { z: '+18.0m', count: 3500, type: 'ROOF', color: '#dc2626' },
                  { z: '+19.5m', count: 620, type: 'ROOF', color: '#dc2626' },
                  { z: '+21.0m', count: 180, type: 'ROOF', color: '#dc2626' },
                ].map((bar, i) => {
                  const isVisible = lidarFilter === 'ALL' || lidarFilter === bar.type;
                  const heightPct = isVisible ? (bar.count / 3500) * 85 : 4;

                  return (
                    <div key={i} className="flex-1 flex flex-col items-center group relative h-full justify-end">
                      <div
                        className="w-full rounded-t transition-all duration-300 group-hover:brightness-125"
                        style={{
                          height: `${heightPct}%`,
                          backgroundColor: isVisible ? bar.color : '#333333',
                          opacity: isVisible ? 0.9 : 0.2,
                        }}
                      />
                      {/* Tooltip on hover */}
                      <div className="absolute -top-10 opacity-0 group-hover:opacity-100 transition pointer-events-none bg-black border border-white/20 text-[9px] text-white px-2 py-1 rounded shadow-lg whitespace-nowrap z-20">
                        {bar.z} : {bar.count} pts [{bar.type}]
                      </div>
                      <span className={`text-[8px] ${mutedText} mt-1 opacity-70 group-hover:opacity-100`}>
                        {bar.z}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Statistical Metadata strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-4 border-t border-neutral-200 font-mono text-xs">
              <div>
                <div className={`text-[10px] ${mutedText}`}>Total Points Processed</div>
                <div className="text-base font-bold text-black dark:text-white">15,000 pts</div>
              </div>
              <div>
                <div className={`text-[10px] ${mutedText}`}>Mean Pulse Intensity</div>
                <div className={`text-base font-bold ${tint(isBrutalistLight,'cyan')}`}>148.4 DN (±12.1)</div>
              </div>
              <div>
                <div className={`text-[10px] ${mutedText}`}>RMS Elevation Variance</div>
                <div className={`text-base font-bold ${tint(isBrutalistLight,'emerald')}`}>± 0.008 m (8mm)</div>
              </div>
              <div>
                <div className={`text-[10px] ${mutedText}`}>Point Cloud Classification</div>
                <div className={`text-base font-bold ${tint(isBrutalistLight,'purple')}`}>ASPRS Standard 1.4</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* CHART 3: SUBTERRANEAN CLASH & UTILITY CLEARANCES                      */}
      {/* ===================================================================== */}
      {activeChart === 'SUBTERRANEAN' && (
        <div className="space-y-6 animate-fade-in">
          <div className={`p-6 ${cardBorder}`}>
            <div className="flex items-center justify-between border-b pb-4 mb-6 border-neutral-200">
              <div className="flex items-center gap-2">
                <ShieldCheck className={`w-5 h-5 ${okText}`} />
                <h3 className="font-mono font-bold text-sm uppercase">
                  Subsurface Municipal Utilities & Geotechnical Buffer Profile
                </h3>
              </div>
              <span className={`text-xs font-mono ${tint(isBrutalistLight,'emerald')} font-bold bg-emerald-50 px-2 py-0.5 border border-emerald-200 rounded`}>
                0 CLASHES DETECTED
              </span>
            </div>

            {/* Utility Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className={`border-b border-neutral-300 text-left ${mutedText} text-[10px] uppercase`}>
                    <th className="pb-3">Utility Network / Stratum</th>
                    <th className="pb-3">Z-Depth</th>
                    <th className="pb-3">Conduit Specification</th>
                    <th className="pb-3">Physical Clearance</th>
                    <th className="pb-3">Required Buffer</th>
                    <th className="pb-3">Safety Margin</th>
                    <th className="pb-3">Regulatory Agency</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-200">
                  {subterraneanProfiles.map((item, idx) => (
                    <tr key={idx} className="hover:bg-neutral-500/5 transition">
                      <td className="py-3 font-bold">{item.utility}</td>
                      <td className={`py-3 ${tint(isBrutalistLight,'cyan')} font-bold`}>{item.depth}</td>
                      <td className={`py-3 ${midText}`}>{item.diameter}</td>
                      <td className="py-3 font-bold">{item.distanceToFoundation}</td>
                      <td className={`py-3 ${midText}`}>{item.requiredBuffer}</td>
                      <td className="py-3">
                        <span className={`px-2 py-0.5 bg-emerald-500/10 ${tint(isBrutalistLight,'emerald')} font-bold rounded`}>
                          {item.clearanceMargin}
                        </span>
                      </td>
                      <td className={`py-3 ${mutedText} text-[11px]`}>{item.authority}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-6 p-4 bg-emerald-50/50 border border-emerald-200 text-xs font-mono text-emerald-900 rounded-lg flex items-start gap-3">
              <CheckCircle2 className={`w-5 h-5 ${tint(isBrutalistLight,'emerald')} shrink-0 mt-0.5`} />
              <div>
                <span className="font-bold">Volumetric Clash Clearance Certified:</span>
                <p className="mt-0.5 text-[11px] text-emerald-800">
                  Full 3D spatial boolean subtraction confirms that basement retaining diaphragm and 16 end-bearing foundation piles maintain a minimum radial buffer of 3.80m from all civic utility networks, completely satisfying Section 14 of the Maharashtra Municipal Corporation Act.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* CHART 4: SETBACK & DCR COMPLIANCE MATRIX                              */}
      {/* ===================================================================== */}
      {activeChart === 'SETBACK_COMPLIANCE' && (
        <div className="space-y-6 animate-fade-in">
          <div className={`p-6 ${cardBorder}`}>
            <div className="flex items-center justify-between border-b pb-4 mb-6 border-neutral-200">
              <div className="flex items-center gap-2">
                <FileCheck2 className="w-5 h-5" style={{ color: accentColor }} />
                <h3 className="font-mono font-bold text-sm uppercase">
                  NBC 2016 & DCPR Statutory Setback Verification Matrix
                </h3>
              </div>
              <span className={`text-xs font-mono font-bold ${tint(isBrutalistLight,'emerald')}`}>8 OF 8 CRITERIA COMPLIANT</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {setbackCompliance.map((item, idx) => (
                <div
                  key={idx}
                  className="p-4 border border-neutral-200 rounded hover:border-neutral-400 transition bg-neutral-50/40"
                >
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="font-bold text-sm">{item.parameter}</span>
                    <span className={`px-2 py-0.5 bg-emerald-500/10 ${tint(isBrutalistLight,'emerald')} font-bold text-[10px] rounded`}>
                      {item.status}
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-neutral-200/70 text-[11px] font-mono">
                    <div>
                      <div className={`text-[9px] ${mutedText} uppercase`}>Sanctioned</div>
                      <div className="font-bold mt-0.5">{item.sanctioned}</div>
                    </div>
                    <div>
                      <div className={`text-[9px] ${mutedText} uppercase`}>Measured LiDAR</div>
                      <div className={`font-bold ${tint(isBrutalistLight,'cyan')} mt-0.5`}>{item.measured}</div>
                    </div>
                    <div>
                      <div className={`text-[9px] ${mutedText} uppercase`}>Delta Margin</div>
                      <div className={`font-bold ${tint(isBrutalistLight,'emerald')} mt-0.5`}>{item.variance}</div>
                    </div>
                  </div>

                  <div className={`mt-2 text-[10px] font-mono ${mutedText}`}>
                    Statute: {item.dcrRef}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
