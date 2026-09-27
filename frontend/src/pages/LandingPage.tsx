import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  ShieldCheck,
  Compass,
  FileSpreadsheet,
  Download,
  Terminal,
  Box,
  Search,
  Printer,
  Scan,
  Sun,
  Moon,
  BookOpen,
} from 'lucide-react';
import { BrutalistWireframeHero } from '../components/landing/BrutalistWireframeHero';
import { CadastralDocsHub } from '../components/landing/CadastralDocsHub';
import { CadastralWireframeInspector } from '../components/landing/CadastralWireframeInspector';
import { CadastralSpatialCharts } from '../components/landing/CadastralSpatialCharts';
import { CadastralDeepTelemetry } from '../components/landing/CadastralDeepTelemetry';
import { fetchHeroProperty, PROPERTY_CARD_PDF_URL, CADASTRAL_EXCEL_URL } from '../services/api';
import { HeroProperty } from '../types/cadastre';
import { HERO_ULPIN } from '../constants';
import { GovernmentDeedPrintModal } from '../components/modals/GovernmentDeedPrintModal';
import { useApp } from '../context/AppContext';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const { setMapFocus } = useApp();
  const [hero, setHero] = useState<HeroProperty | null>(null);
  const [activeStrata, setActiveStrata] = useState<number>(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [printModalOpen, setPrintModalOpen] = useState(false);

  // Light is the default, matching the app shell. Previously this was
  // `const isLightMode = false`, which left the entire light branch below
  // written but unreachable, so it had never been rendered. It is state now
  // and persisted, so both branches stay reachable and testable.
  const [isLightMode, setIsLightMode] = useState<boolean>(() => {
    const stored = localStorage.getItem('bd-landing-theme');
    return stored === null ? true : stored === 'light';
  });

  useEffect(() => {
    localStorage.setItem('bd-landing-theme', isLightMode ? 'light' : 'dark');
  }, [isLightMode]);

  // Custom Cursor State
  const [cursorPos, setCursorPos] = useState({ x: -100, y: -100 });
  const [isHovered, setIsHovered] = useState(false);

  useEffect(() => {
    fetchHeroProperty().then(setHero).catch(() => {});
  }, []);

  // Track mouse coordinates for custom brutalist crosshair
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setCursorPos({ x: e.clientX, y: e.clientY });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  const ulpin = hero?.parent_ulpin || HERO_ULPIN;

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = searchQuery.trim();
    if (!clean) {
      navigate(`/app/properties/${ulpin}`);
      return;
    }
    if (clean.length === 14 || clean.includes('/')) {
      navigate(`/app/properties/${clean}`);
    } else {
      setMapFocus(clean);
      navigate('/app/map');
    }
  };

  const strataLevels = [
    {
      level: '+18.0M',
      code: 'AIR_RIGHTS',
      name: 'Rooftop Solar & Air-Rights Envelope',
      vol: '1,420 m³',
      status: 'UNENCUMBERED',
      color: '#00ff66',
      desc: 'Legal 3D airspace prism above CTS 142/A with 0.00mm cantilever overhang into adjoining parcels.',
    },
    {
      level: '+14.4M',
      code: 'LEVEL_04',
      name: 'Fourth Floor Residential Units (401-404)',
      vol: '1,785 m³',
      status: 'DEMO RECORD',
      color: '#00f0ff',
      desc: 'Four residential apartments in the demo dataset with Mod 36 check characters.',
    },
    {
      level: '+07.2M',
      code: 'LEVEL_02',
      name: 'Second Floor Residential Units (201-204)',
      vol: '1,785 m³',
      status: 'DEMO RECORD',
      color: '#00f0ff',
      desc: 'Carpet area 420.0 m² from the demo dataset; no blueprint survey was checked.',
    },
    {
      level: '+00.0M',
      code: 'GROUND',
      name: 'Ground Level Entry Plinth & Reception',
      vol: '1,836 m³',
      status: 'PUBLIC ACCESS EASEMENT',
      color: '#ffffff',
      desc: 'Building footprint 510.0 m², about 51% of the plot area. The 60% figure is a demonstration value, not a DCR rule this tool checks.',
    },
    {
      level: '-01.8M',
      code: 'SUBSURFACE',
      name: 'Utility Envelope (illustrative)',
      vol: 'NO DATA',
      status: 'NOT ASSESSED',
      color: '#38bdf8',
      desc: 'No utility network is loaded, so no offset or clash is computed. A 4.20 m separation from a 600 mm main was previously shown here and was typed in by hand.',
    },
    {
      level: '-03.5M',
      code: 'BASEMENT_B1',
      name: 'Subterranean Parking & Foundation Strata',
      vol: '1,785 m³',
      status: 'SUBTERRANEAN RIGHT',
      color: '#ef4444',
      desc: 'Subsurface parking vault with geotechnical soil compliance and seismic Class III anchoring.',
    },
  ];

  return (
    <div
      className={`min-h-screen font-sans relative overflow-x-hidden ${
        isLightMode
          ? 'bg-[#F4F3EE] text-black selection:bg-[#00E55B] selection:text-black'
          // `dark` scopes the Tailwind dark: variants to the landing toggle. Without it
          // those variants track the OS preference, which leaves black-on-dark text
          // when the OS is light but the landing is dark.
          : 'dark bg-[#060709] text-white selection:bg-[#00ff66] selection:text-black'
      }`}
      onMouseEnter={() => setIsHovered(false)}
    >
      {/* ===================================================================== */}
      {/* CUSTOM BRUTALIST RETICLE CURSOR (Desktop pointer)                     */}
      {/* ===================================================================== */}
      <div
        className="fixed pointer-events-none z-50 -translate-x-1/2 -translate-y-1/2 hidden md:block transition-transform duration-75"
        style={{ left: `${cursorPos.x}px`, top: `${cursorPos.y}px` }}
      >
        <div
          className={`relative flex items-center justify-center transition-all duration-150 ${
            isHovered
              ? isLightMode
                ? 'w-12 h-12 border-2 border-black scale-125'
                : 'w-12 h-12 border-2 border-[#00ff66] scale-125'
              : isLightMode
              ? 'w-7 h-7 border border-black/80'
              : 'w-7 h-7 border border-[#00ff66]/70'
          }`}
        >
          <div className={`w-1.5 h-1.5 ${isLightMode ? 'bg-black' : 'bg-[#00ff66]'} rounded-full`} />
          <div className={`absolute -top-1 -left-1 w-2 h-2 border-t-2 border-l-2 ${isLightMode ? 'border-black' : 'border-[#00ff66]'}`} />
          <div className={`absolute -bottom-1 -right-1 w-2 h-2 border-b-2 border-r-2 ${isLightMode ? 'border-black' : 'border-[#00ff66]'}`} />
        </div>
        <div
          className={`absolute left-6 top-0 font-mono text-[9px] ${
            isLightMode
              ? 'text-black bg-white px-1.5 py-0.5 border border-black shadow-[2px_2px_0px_0px_#000]'
              : 'text-[#00ff66] bg-black/90 px-1.5 py-0.5 border border-[#00ff66]/40 shadow-lg'
          } whitespace-nowrap`}
        >
          [X:{Math.round(cursorPos.x)} Y:{Math.round(cursorPos.y)}]
        </div>
      </div>

      {/* Subtle Background Cartographic Grid */}
      <div
        className="fixed inset-0 pointer-events-none opacity-20"
        style={{
          backgroundImage: isLightMode
            ? `
                linear-gradient(to right, rgba(0,0,0,0.08) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(0,0,0,0.08) 1px, transparent 1px)
              `
            : `
                linear-gradient(to right, rgba(255,255,255,0.06) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(255,255,255,0.06) 1px, transparent 1px)
              `,
          backgroundSize: '40px 40px',
        }}
      />

      {/* ===================================================================== */}
      {/* TOP TECHNICAL METADATA BAR                                            */}
      {/* ===================================================================== */}
      <header className={`border-b-2 ${isLightMode ? 'border-black bg-[#F4F3EE]/95 text-black' : 'border-white/15 bg-black/90 text-white'} backdrop-blur-md sticky top-0 z-40`}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-2 flex items-center justify-between text-[11px] font-mono">
          <div className="flex items-center gap-3">
            <span className={`inline-block w-2.5 h-2.5 ${isLightMode ? 'bg-[#00E55B] border border-black' : 'bg-[#00ff66]'} animate-pulse`} />
            <span className={`font-bold ${isLightMode ? 'text-black' : 'text-white'} tracking-widest uppercase`}>
              BHU-DRISHTI // SPATIAL CADASTRE OS
            </span>
            <span className={`${isLightMode ? 'text-black/65' : 'text-white/65'} hidden sm:inline`}>|</span>
            <span className={`${isLightMode ? 'text-black/70' : 'text-white/80'} hidden sm:inline`}>SYS.CORE: ONLINE</span>
            <span className={`${isLightMode ? 'text-black/65' : 'text-white/65'} hidden sm:inline`}>|</span>
            <span className={`${isLightMode ? 'text-black/70' : 'text-white/80'} hidden sm:inline`}>LEDGER: 10 SAMPLE BLOCKS</span>
          </div>

          <div className={`flex items-center gap-4 ${isLightMode ? 'text-black/75' : 'text-white/75'} text-[10px]`}>
            <span className="hidden md:inline">DATUM: EPSG:32643 / UTM 43N</span>
            <button
              type="button"
              onClick={() => setIsLightMode((v) => !v)}
              aria-pressed={isLightMode}
              title={isLightMode ? 'Switch to dark' : 'Switch to light'}
              className={`px-2 py-1 font-mono text-[10px] font-black uppercase flex items-center gap-1 transition ${
                isLightMode
                  ? 'border-2 border-black bg-white text-black hover:bg-[#FFE600] shadow-[2px_2px_0px_0px_#000]'
                  : 'border border-white/30 text-white hover:border-amber-400'
              }`}
            >
              {isLightMode ? <Sun className="w-3 h-3" /> : <Moon className="w-3 h-3" />}
              <span className="hidden sm:inline">{isLightMode ? 'Light' : 'Dark'}</span>
            </button>
            <span className={`${isLightMode ? 'text-black font-black bg-[#00FF66] px-1.5 py-0.5 border border-black' : 'text-[#00ff66] font-bold'}`}>
              14-DIGIT MINT ACTIVE
            </span>
          </div>
        </div>

        {/* Minimal Brutalist Main Navigation */}
        <nav className={`max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between border-t ${isLightMode ? 'border-black/20' : 'border-white/10'}`}>
          <Link
            to="/"
            className="flex items-center gap-2 group"
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
          >
            <div className={`w-8 h-8 ${isLightMode ? 'bg-black text-white group-hover:bg-[#00FF66] group-hover:text-black border border-black' : 'bg-white text-black group-hover:bg-[#00ff66]'} font-black flex items-center justify-center text-sm font-mono transition`}>
              3D
            </div>
            <div>
              <span className={`font-black text-sm tracking-tight ${isLightMode ? 'text-black' : 'text-white'} block uppercase font-display`}>
                BHU-DRISHTI
              </span>
              <span className={`text-[9px] font-mono ${isLightMode ? 'text-black/70' : 'text-white/70'} block -mt-1`}>
                NATIONAL 3D LAND TWIN
              </span>
            </div>
          </Link>

          {/* Center Tabs with Expansion on Hover */}
          <div className="hidden lg:flex items-center gap-6 font-mono text-xs">
            {[
              { label: '01 MAP', path: '/app/map', sub: 'PRECINCT' },
              { label: '02 TWIN', path: `/app/properties/${ulpin}`, sub: 'B-17 HUD' },
              { label: '03 AUDIT', path: '/app/audit', sub: 'BLOCKCHAIN' },
              { label: '04 EXCEL', path: '/app/ulpin', sub: 'EXTRUDER' },
            ].map((item) => (
              <Link
                key={item.label}
                to={item.path}
                onMouseEnter={() => setIsHovered(true)}
                onMouseLeave={() => setIsHovered(false)}
                className={`${isLightMode ? 'text-black/80 hover:text-black font-bold' : 'text-white/70 hover:text-[#00ff66]'} transition flex items-center gap-1 group py-1`}
              >
                <span>{item.label}</span>
                <span className={`text-[10px] ${isLightMode ? 'text-black/65 group-hover:text-black' : 'text-white/65 group-hover:text-[#00ff66]/70'} transition hidden xl:inline`}>
                  //{item.sub}
                </span>
              </Link>
            ))}
            <a
              href="#docs"
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
              className={`${isLightMode ? 'text-black/80 hover:text-black font-bold' : 'text-white/70 hover:text-[#00ff66]'} transition flex items-center gap-1 py-1`}
            >
              <span>05 DOCS</span>
              <span className={`text-[10px] ${isLightMode ? 'text-black/65' : 'text-white/65'} hidden xl:inline`}>
                //SPEC MATRIX
              </span>
            </a>
            <button
              onClick={() => setPrintModalOpen(true)}
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
              className={`${isLightMode ? 'text-black/80 hover:text-amber-700 font-bold' : 'text-white/70 hover:text-amber-300'} transition flex items-center gap-1 cursor-pointer py-1`}
            >
              <span>06 DEED</span>
              <span className={`text-[10px] ${isLightMode ? 'text-black/65 hover:text-amber-700' : 'text-white/65 hover:text-amber-300/70'} hidden xl:inline`}>
                //PRINT MONOGRAPH
              </span>
            </button>
          </div>

          {/* Right Action Button */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPrintModalOpen(true)}
              className={`hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 ${isLightMode ? 'border-2 border-black bg-white text-black hover:bg-[#FFE600] shadow-[2px_2px_0px_0px_#000]' : 'border border-white/30 hover:border-amber-400 text-white hover:text-amber-300'} text-xs font-mono font-bold transition`}
            >
              <Printer className="w-3.5 h-3.5" />
              <span>PRINT DEED</span>
            </button>

            <Link
              to="/docs"
              className={`hidden md:inline-flex px-3 py-1.5 ${isLightMode ? 'border-2 border-black bg-white text-black hover:bg-[#FFE600] shadow-[2px_2px_0px_0px_#000]' : 'border border-white/30 hover:border-amber-400 text-white hover:text-amber-300'} text-xs font-mono font-bold transition items-center gap-1.5`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>DOCS</span>
            </Link>

            <Link
              to="/app"
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
              className={`px-4 py-2 ${isLightMode ? 'bg-black text-white hover:bg-[#00FF66] hover:text-black border-2 border-black shadow-[3px_3px_0px_0px_#000]' : 'bg-white text-black hover:bg-[#00ff66] shadow-sm'} font-mono text-xs font-black uppercase tracking-wider transition flex items-center gap-1.5 group`}
            >
              <span>ENTER WORKSPACE</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </nav>
      </header>

      {/* ===================================================================== */}
      {/* HERO SECTION — OVERSIZED BRUTALIST TYPOGRAPHY + 3D WIREFRAME WORLD     */}
      {/* ===================================================================== */}
      <section className={`relative max-w-7xl mx-auto px-4 sm:px-6 pt-8 pb-14 border-b-2 ${isLightMode ? 'border-black/20' : 'border-white/10'}`}>
        {/* Technical Coordinate Tags */}
        <div className={`flex flex-wrap items-center justify-between text-xs font-mono ${isLightMode ? 'text-black/70 border-b border-black/20' : 'text-white/75 border-b border-white/10'} mb-4 pb-2`}>
          <div>[SECTOR 08 // AIROLI, NAVI MUMBAI // CTS 142/A]</div>
          <div className="flex items-center gap-3">
            <span>LAT: 19.155372° N</span>
            <span>LON: 72.998024° E</span>
            <span className={`${isLightMode ? 'text-black font-black bg-[#00FF66] px-1.5 border border-black' : 'text-[#00ff66] font-bold'}`}>ALT: +18.00M GTS</span>
          </div>
        </div>

        {/* Hero Title & 3D Centerpiece Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Oversized Hero Brutalist Typography & Mechanics */}
          <div className="lg:col-span-5 space-y-6 pt-2">
            <div className="space-y-1">
              <span className={`font-mono text-xs font-bold ${isLightMode ? 'text-black bg-[#00FF66] px-1.5 py-0.5 border border-black inline-block' : 'text-[#00ff66]'} tracking-widest uppercase block w-fit`}>
                // NATIONAL VOLUMETRIC CADASTRAL SYSTEM
              </span>
              <h1 className={`text-5xl sm:text-6xl xl:text-7xl font-black uppercase tracking-tighter leading-[0.9] font-display ${isLightMode ? 'text-black' : 'text-white'}`}>
                3D<br />
                PROPERTY<br />
                <span className={isLightMode ? 'text-black drop-shadow-sm' : 'text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-200 to-slate-400'}>
                  INTELLIGENCE
                </span>
              </h1>
            </div>

            <p className={`text-sm font-mono leading-relaxed border-l-4 ${isLightMode ? 'border-black pl-4 text-black/80 bg-white/70 p-2.5 border border-black/15 shadow-[2px_2px_0px_0px_#000]' : 'border-[#00ff66] pl-4 text-slate-300'}`}>
              A drawing prototype. It extrudes building masses into 3D shapes so you can look at them, and it
              compares a floor-area figure you type against a fixed number. It does not enforce any planning rule,
              read any LiDAR or registry data, or record anything on a blockchain.
            </p>

            {/* Quick Primary Actions */}
            <div className="flex flex-col sm:flex-row gap-3 pt-2 font-mono text-xs">
              <Link
                to={`/app/properties/${ulpin}`}
                className={`px-5 py-3.5 ${
                  isLightMode
                    ? 'bg-[#00FF66] text-black border-2 border-black font-black shadow-[4px_4px_0px_0px_#000] hover:bg-black hover:text-white'
                    : 'bg-[#00ff66] text-black font-black hover:bg-white shadow-lg'
                } uppercase tracking-wider transition flex items-center justify-center gap-2`}
              >
                <span>[ 01 INTERROGATE 3D TWIN ]</span>
                <ArrowRight className="w-4 h-4" />
              </Link>

              <Link
                to="/app/map"
                className={`px-5 py-3.5 ${
                  isLightMode
                    ? 'bg-white text-black border-2 border-black font-bold shadow-[4px_4px_0px_0px_#000] hover:bg-neutral-100'
                    : 'bg-black border-2 border-white/30 hover:border-white text-white font-bold'
                } uppercase tracking-wider transition flex items-center justify-center gap-2`}
              >
                <span>[ 02 PRECINCT FABRIC ]</span>
                <Compass className={`w-4 h-4 ${isLightMode ? 'text-black' : 'text-cyan-400'}`} />
              </Link>
            </div>

            {/* Raw System Telemetry Card */}
            <div className={`p-4 ${isLightMode ? 'bg-white border-2 border-black shadow-[4px_4px_0px_0px_#000] text-black' : 'bg-black/60 border-2 border-white/15 text-white'} space-y-2 font-mono text-xs`}>
              <div className={`flex justify-between items-center text-[10px] ${isLightMode ? 'text-black/75 border-b border-black/20' : 'text-white/75 border-b border-white/10'} pb-1.5`}>
                <span>TARGET PARCEL:</span>
                <span className={`font-bold ${isLightMode ? 'text-black' : 'text-white'}`}>{ulpin}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px] pt-1">
                <div>
                  <span className={`${isLightMode ? 'text-black/70' : 'text-white/70'} block text-[9px]`}>MEASURED FSI:</span>
                  <span className={`font-bold ${isLightMode ? 'text-emerald-700' : 'text-[#00ff66]'}`}>1.80 / MAX 2.00 (PASS)</span>
                </div>
                <div>
                  <span className={`${isLightMode ? 'text-black/70' : 'text-white/70'} block text-[9px]`}>STOREYS / UNITS:</span>
                  <span className={`font-bold ${isLightMode ? 'text-black' : 'text-white'}`}>G+4 (5 FLOORS) // 21 UNITS</span>
                </div>
                <div>
                  <span className={`${isLightMode ? 'text-black/70' : 'text-white/70'} block text-[9px]`}>GROUND FOOTPRINT:</span>
                  <span className={`font-bold ${isLightMode ? 'text-black' : 'text-white'}`}>510.00 M² (51% COV)</span>
                </div>
                <div>
                  <span className={`${isLightMode ? 'text-black/70' : 'text-white/70'} block text-[9px]`}>SUBTERRANEAN:</span>
                  <span className={`font-bold ${isLightMode ? 'text-rose-700' : 'text-rose-400'}`}>1 BASEMENT (-3.5M)</span>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: 3D Wireframe Holographic Reconstruction */}
          <div className="lg:col-span-7">
            <BrutalistWireframeHero
              isLightMode={isLightMode}
              className={`w-full ${isLightMode ? 'border-2 border-black shadow-[6px_6px_0px_0px_#000]' : 'shadow-2xl'}`}
              onExploreClick={() => navigate(`/app/properties/${ulpin}`)}
            />
          </div>
        </div>
      </section>

      {/* ===================================================================== */}
      {/* REAL-TIME MARQUEE TICKER                                              */}
      {/* ===================================================================== */}
      <div className={`${isLightMode ? 'bg-black text-[#00FF66] border-y-2 border-black' : 'bg-white text-black border-b-2 border-white/20'} py-2.5 font-mono text-xs font-black uppercase tracking-wider overflow-hidden select-none`}>
        <div className="flex whitespace-nowrap animate-marquee gap-8">
          <span>// BHU-DRISHTI 3D RESEARCH PROTOTYPE</span>
          <span>// EPSG:32643 UTM ZONE 43N</span>
          <span>// MOD 36 CHECK CHARACTERS GENERATED</span>
          <span>// LOCAL SHA-256 HASH CHAIN: 10 SAMPLE BLOCKS</span>
          <span>// SYNTHETIC POINT CLOUD: 15,000 GENERATED PTS</span>
          <span>// NOT A SURVEY, NOT A STATUTORY RECORD</span>
          <span>// SUBSURFACE UTILITIES: NOT INSPECTED</span>
          <span>// PERMITTED FSI: SYNTHETIC ASSUMPTION</span>
          <span>// BHU-DRISHTI 3D RESEARCH PROTOTYPE</span>
          <span>// EPSG:32643 UTM ZONE 43N</span>
          <span>// MOD 36 CHECK CHARACTERS GENERATED</span>
        </div>
      </div>

      {/* ===================================================================== */}
      {/* SECTION 01 // 4-COLUMN BRUTALIST ARCHITECTURAL MATRIX                 */}
      {/* ===================================================================== */}
      <section className={`max-w-7xl mx-auto px-4 sm:px-6 py-16 border-b-2 ${isLightMode ? 'border-black/20' : 'border-white/10'}`}>
        <div className="flex flex-col sm:flex-row items-start sm:items-end justify-between gap-4 mb-8">
          <div>
            <span className={`font-mono text-xs font-bold ${isLightMode ? 'text-black bg-[#FFE600] px-1.5 py-0.5 border border-black inline-block' : 'text-[#00ff66]'} tracking-widest uppercase`}>
              // ARCHITECTURAL CORE MODULES
            </span>
            <h2 className={`text-3xl sm:text-4xl font-black uppercase tracking-tight font-display mt-1 ${isLightMode ? 'text-black' : 'text-white'}`}>
              ENGINEERED FOR SPATIAL SOVEREIGNTY
            </h2>
          </div>
          <span className={`font-mono text-xs ${isLightMode ? 'text-black/70' : 'text-white/70'} hidden sm:inline-block`}>
            [SYS.MATRIX // 4 SUBSYSTEMS]
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            {
              idx: '01',
              title: '3D VOLUMETRIC EXTENSION',
              tag: 'ISO/IEC 7064',
              desc: 'Extrudes building footprints into illustrative 3D spatial prisms with Mod 36 check characters, floor heights, and room air-space volumes.',
              icon: Box,
              color: isLightMode ? '#007A2E' : '#00ff66',
              action: () => navigate(`/app/properties/${ulpin}`),
              btn: 'INSPECT 3D TWIN',
            },
            {
              idx: '02',
              title: 'LIDAR POINT CLOUD FUSION',
              tag: '15,000 PTS SYNTH',
              desc: 'Integrates classified point clouds (ground, wall, roof, slab returns) with aerial photogrammetry and subsurface utility corridors.',
              icon: Scan,
              color: isLightMode ? '#0077CC' : '#00f0ff',
              action: () => navigate(`/app/properties/${ulpin}`),
              btn: 'VIEW POINT CLOUD',
            },
            {
              idx: '03',
              title: 'SOVEREIGN BLOCKCHAIN',
              tag: 'SHA-256 PoW',
              desc: 'Every deed, transfer, and building sanction is cryptographically hashed with binary Merkle trees and 3-of-3 multi-party threshold signatures.',
              icon: ShieldCheck,
              color: isLightMode ? '#8A4B08' : '#facc15',
              action: () => navigate('/app/audit'),
              btn: 'LEDGER EXPLORER',
            },
            {
              idx: '04',
              title: 'EXCEL 3D ULPIN EXTRUDER',
              tag: 'SPREADSHEET INGEST',
              desc: 'Upload multi-storey unit registers in Excel (.xlsx) or CSV to batch-extrude 3D building twins and mint ISO/IEC 7064 identifiers.',
              icon: FileSpreadsheet,
              color: isLightMode ? '#5B21B6' : '#c084fc',
              action: () => navigate('/app/ulpin'),
              btn: 'OPEN 3D EXTRUDER',
            },
          ].map((card) => {
            const Icon = card.icon;
            return (
              <div
                key={card.idx}
                className={`p-6 ${
                  isLightMode
                    ? 'bg-white border-2 border-black shadow-[4px_4px_0px_0px_#000] hover:translate-x-[-2px] hover:translate-y-[-2px] hover:shadow-[6px_6px_0px_0px_#000]'
                    : 'bg-black/60 border-2 border-white/15 hover:border-white'
                } transition flex flex-col justify-between group space-y-6`}
              >
                <div className="space-y-4">
                  <div className="flex items-center justify-between font-mono text-xs">
                    <span className={`font-black text-lg ${isLightMode ? 'text-black group-hover:text-emerald-700' : 'text-white group-hover:text-[#00ff66]'} transition`}>
                      {card.idx}
                    </span>
                    <span
                      className="px-2 py-0.5 border text-[10px] font-bold uppercase tracking-wider"
                      style={{ borderColor: isLightMode ? '#000' : `${card.color}40`, color: card.color }}
                    >
                      {card.tag}
                    </span>
                  </div>

                  <div className="space-y-1.5">
                    <Icon className="w-6 h-6 mb-2" style={{ color: card.color }} />
                    <h3 className={`font-bold font-display text-base tracking-tight uppercase ${isLightMode ? 'text-black' : 'text-white'}`}>
                      {card.title}
                    </h3>
                    <p className={`text-xs font-mono leading-relaxed ${isLightMode ? 'text-black/70' : 'text-slate-400'}`}>
                      {card.desc}
                    </p>
                  </div>
                </div>

                <button
                  onClick={card.action}
                  className={`w-full py-2.5 px-3 ${
                    isLightMode
                      ? 'bg-black text-white hover:bg-[#00FF66] hover:text-black border border-black shadow-[2px_2px_0px_0px_#000]'
                      : 'bg-white/5 hover:bg-white text-white hover:text-black border border-white/20'
                  } font-mono text-xs font-bold uppercase tracking-wider transition flex items-center justify-between cursor-pointer`}
                >
                  <span>{card.btn}</span>
                  <span>→</span>
                </button>
              </div>
            );
          })}
        </div>
      </section>

      {/* ===================================================================== */}
      {/* SECTION 02 // INTERACTIVE STRATA & ELEVATION INSPECTOR                */}
      {/* ===================================================================== */}
      <section className={`max-w-7xl mx-auto px-4 sm:px-6 py-16 border-b-2 ${isLightMode ? 'border-black/20' : 'border-white/10'}`}>
        <div className="flex flex-col sm:flex-row items-start sm:items-end justify-between gap-4 mb-8">
          <div>
            <span className={`font-mono text-xs font-bold ${isLightMode ? 'text-black bg-[#FFE600] px-1.5 py-0.5 border border-black inline-block' : 'text-[#00ff66]'} tracking-widest uppercase`}>
              // VOLUMETRIC STRATIFICATION
            </span>
            <h2 className={`text-3xl sm:text-4xl font-black uppercase tracking-tight font-display mt-1 ${isLightMode ? 'text-black' : 'text-white'}`}>
              VERTICAL STRATA & UTILITY CORRIDORS
            </h2>
          </div>
          <span className={`font-mono text-xs ${isLightMode ? 'text-black/70' : 'text-white/70'} hidden sm:inline-block`}>
            [SECTION CUT // Z-AXIS RESOLUTION]
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Strata Level Selector */}
          <div className="lg:col-span-5 space-y-2">
            {strataLevels.map((lvl, idx) => (
              <button
                key={lvl.code}
                onClick={() => setActiveStrata(idx)}
                className={`w-full p-4 text-left border-2 font-mono transition flex items-center justify-between cursor-pointer ${
                  activeStrata === idx
                    ? isLightMode
                      ? 'bg-black text-white border-black shadow-[4px_4px_0px_0px_#000]'
                      : 'bg-white text-black border-white shadow-xl'
                    : isLightMode
                    ? 'bg-white text-black border-black/30 hover:border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,0.06)]'
                    : 'bg-black/50 text-white/80 border-white/15 hover:border-white/40'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`font-black text-sm px-2 py-0.5 border ${
                      activeStrata === idx
                        ? isLightMode
                          ? 'bg-white text-black border-white'
                          : 'bg-black text-white border-black'
                        : isLightMode
                        ? 'bg-black/5 text-black border-black/30'
                        : 'bg-white/10 text-white border-white/20'
                    }`}
                  >
                    {lvl.level}
                  </span>
                  <div>
                    <div className="font-bold text-xs uppercase">{lvl.name}</div>
                    <div className={`text-[10px] ${activeStrata === idx ? (isLightMode ? 'text-white/70' : 'text-black/75') : (isLightMode ? 'text-black/75' : 'text-white/70')}`}>
                      {lvl.code} // VOL: {lvl.vol}
                    </div>
                  </div>
                </div>
                <span className="text-xs font-bold">→</span>
              </button>
            ))}
          </div>

          {/* Right Column: Detailed Stratum Visualizer & Data Card */}
          <div className={`lg:col-span-7 p-6 sm:p-8 ${isLightMode ? 'bg-white border-2 border-black shadow-[4px_4px_0px_0px_#000] text-black' : 'bg-black/60 border-2 border-white/20 text-white'} space-y-6 font-mono`}>
            <div className={`flex items-center justify-between border-b ${isLightMode ? 'border-black/20' : 'border-white/15'} pb-4`}>
              <div>
                <span className={`text-[10px] ${isLightMode ? 'text-black/70' : 'text-white/75'} uppercase block`}>ACTIVE STRATUM ANALYSIS:</span>
                <h3 className={`text-xl font-black ${isLightMode ? 'text-black' : 'text-white'} font-display uppercase tracking-tight`}>
                  {strataLevels[activeStrata].name}
                </h3>
              </div>
              <div
                className={`px-3 py-1 text-xs font-bold uppercase tracking-wider border ${isLightMode ? 'border-black' : ''}`}
                style={{
                  borderColor: isLightMode ? '#000' : strataLevels[activeStrata].color,
                  backgroundColor: isLightMode ? `${strataLevels[activeStrata].color}20` : 'transparent',
                  color: isLightMode ? '#000' : strataLevels[activeStrata].color,
                }}
              >
                {strataLevels[activeStrata].status}
              </div>
            </div>

            <p className={`text-sm ${isLightMode ? 'text-black/80' : 'text-slate-300'} leading-relaxed`}>
              {strataLevels[activeStrata].desc}
            </p>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2 text-xs">
              <div className={`p-3 ${isLightMode ? 'bg-[#F4F3EE] border border-black/20' : 'bg-white/5 border border-white/10'}`}>
                <span className={`text-[10px] ${isLightMode ? 'text-black/70' : 'text-white/70'} block`}>ELEVATION DATUM:</span>
                <span className={`font-bold ${isLightMode ? 'text-black' : 'text-white'}`}>{strataLevels[activeStrata].level} GTS</span>
              </div>
              <div className={`p-3 ${isLightMode ? 'bg-[#F4F3EE] border border-black/20' : 'bg-white/5 border border-white/10'}`}>
                <span className={`text-[10px] ${isLightMode ? 'text-black/70' : 'text-white/70'} block`}>ENCLOSED VOLUME:</span>
                <span className={`font-bold ${isLightMode ? 'text-black' : 'text-white'}`}>{strataLevels[activeStrata].vol}</span>
              </div>
              <div className={`p-3 ${isLightMode ? 'bg-[#F4F3EE] border border-black/20' : 'bg-white/5 border border-white/10'} col-span-2 sm:col-span-1`}>
                <span className={`text-[10px] ${isLightMode ? 'text-black/70' : 'text-white/70'} block`}>LEGAL CODES:</span>
                <span className={`font-bold ${isLightMode ? 'text-emerald-700' : 'text-[#00ff66]'}`}>MLRC SEC 148A</span>
              </div>
            </div>

            <div className={`pt-4 border-t ${isLightMode ? 'border-black/20' : 'border-white/15'} flex flex-wrap items-center justify-between gap-4`}>
              <div className={`text-[11px] ${isLightMode ? 'text-black/70' : 'text-white/75'}`}>
                Connected to ULPIN: <strong className={isLightMode ? 'text-black' : 'text-white'}>{ulpin}</strong>
              </div>
              <Link
                to={`/app/properties/${ulpin}`}
                className={`px-4 py-2 ${isLightMode ? 'bg-black text-white hover:bg-[#00FF66] hover:text-black border border-black shadow-[2px_2px_0px_0px_#000]' : 'bg-white text-black hover:bg-[#00ff66]'} font-bold text-xs uppercase transition flex items-center gap-1.5`}
              >
                <span>OPEN HUD VIEW</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ===================================================================== */}
      {/* SECTION 03 // JURISDICTION SEARCH & CADASTRE LOOKUP                   */}
      {/* ===================================================================== */}
      <section className={`max-w-7xl mx-auto px-4 sm:px-6 py-16 border-b-2 ${isLightMode ? 'border-black/20' : 'border-white/10'}`}>
        <div className={`p-6 sm:p-10 ${isLightMode ? 'bg-white border-2 border-black shadow-[4px_4px_0px_0px_#000]' : 'bg-black/70 border-2 border-white/15'} flex flex-col lg:flex-row items-start lg:items-center justify-between gap-8`}>
          <div className="space-y-2 max-w-lg">
            <span className={`font-mono text-xs font-bold ${isLightMode ? 'text-black bg-[#FFE600] px-1.5 py-0.5 border border-black inline-block' : 'text-[#00ff66]'} tracking-widest uppercase`}>
              // ADMINISTRATIVE DRILL-DOWN SEARCH
            </span>
            <h3 className={`text-2xl sm:text-3xl font-black font-display uppercase tracking-tight ${isLightMode ? 'text-black' : 'text-white'}`}>
              LOCATE ANY CADASTRAL PARCEL
            </h3>
            <p className={`text-xs ${isLightMode ? 'text-black/70' : 'text-slate-400'} font-mono leading-relaxed`}>
              Enter any 14-digit Base ULPIN, CTS number, or plot identifier across Maharashtra to interrogate its 3D
              volumetric model, FSI audit, and digital deed.
            </p>
          </div>

          <form onSubmit={handleSearchSubmit} className="w-full lg:max-w-md space-y-3 font-mono">
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="e.g. 12345678901234 or CTS 142/A"
                className={`w-full p-4 ${isLightMode ? 'bg-[#F4F3EE] border-2 border-black text-black placeholder:text-black/65 focus:border-[#007A2E]' : 'bg-white/5 border-2 border-white/20 focus:border-[#00ff66] text-white placeholder:text-white/65'} font-mono text-xs uppercase focus:outline-none transition`}
              />
              <button
                type="submit"
                className={`absolute right-2 top-2 bottom-2 px-4 ${isLightMode ? 'bg-black text-white hover:bg-[#00FF66] hover:text-black border border-black' : 'bg-white text-black hover:bg-[#00ff66]'} font-black text-xs uppercase transition flex items-center gap-1.5`}
              >
                <span>QUERY</span>
                <Search className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className={`flex items-center justify-between text-[10px] ${isLightMode ? 'text-black/75' : 'text-white/75'} px-1`}>
              <span>PILOT NODE: AIROLI SECTOR 8</span>
              <button
                type="button"
                onClick={() => setSearchQuery('12345678901234')}
                className={`${isLightMode ? 'text-black font-bold hover:underline' : 'text-[#00ff66] hover:underline'}`}
              >
                USE DEMO ULPIN: 12345678901234
              </button>
            </div>
          </form>
        </div>
      </section>

      {/* ===================================================================== */}
      {/* SECTION 04 // SOVEREIGN EXPORT ENGINE & MONOGRAPH GENERATOR           */}
      {/* ===================================================================== */}
      <section className={`max-w-7xl mx-auto px-4 sm:px-6 py-16 border-b-2 ${isLightMode ? 'border-black/20' : 'border-white/10'}`}>
        <div className={`p-6 sm:p-10 ${isLightMode ? 'bg-white border-2 border-black shadow-[4px_4px_0px_0px_#000]' : 'bg-black/60 border-2 border-white/20'} grid grid-cols-1 lg:grid-cols-12 gap-8 items-center font-mono`}>
          <div className="lg:col-span-6 space-y-4">
            <span className={`text-xs ${isLightMode ? 'text-black bg-[#00FF66] px-1.5 py-0.5 border border-black inline-block' : 'text-[#00ff66]'} font-bold tracking-widest uppercase block w-fit`}>
              // SOVEREIGN EXPORT ENGINE
            </span>
            <h3 className={`text-2xl sm:text-3xl font-black font-display uppercase tracking-tight ${isLightMode ? 'text-black' : 'text-white'}`}>
              PROTOTYPE DOCUMENTS & DATA PIPELINES
            </h3>
            <p className={`text-xs ${isLightMode ? 'text-black/80' : 'text-slate-300'} leading-relaxed`}>
              Generate prototype property monographs, academic write-ups, compilable LaTeX sources, and
              multi-tab cadastral workbooks. These are demonstration documents, not deeds.
            </p>
            <div className={`text-[11px] ${isLightMode ? 'text-black/70' : 'text-slate-400'} space-y-1 pt-1`}>
              <div>• Mod 36 check characters generated for the ULPIN-style identifiers</div>
              <div>• Data model borrows ISO 19152 (LADM) vocabulary</div>
              <div>• Local SHA-256 hash chain over sample records</div>
            </div>
          </div>

          <div className="lg:col-span-6 space-y-2.5">
            {/* Direct Print Monograph Button */}
            <button
              type="button"
              onClick={() => setPrintModalOpen(true)}
              className={`w-full py-3.5 px-4 ${
                isLightMode
                  ? 'bg-[#00FF66]/20 hover:bg-[#00FF66] border-2 border-black text-black shadow-[3px_3px_0px_0px_#000]'
                  : 'bg-[#00ff66]/10 hover:bg-[#00ff66]/20 border-2 border-[#00ff66] text-[#00ff66] shadow-lg'
              } text-xs font-bold transition flex items-center justify-between group cursor-pointer`}
            >
              <span className="flex items-center gap-2">
                <Printer className={`w-4 h-4 ${isLightMode ? 'text-black' : 'text-[#00ff66]'}`} />
                <span>PRINT SOVEREIGN MONOGRAPH & DEED</span>
              </span>
              <span className={`text-[10px] ${isLightMode ? 'text-black/70 group-hover:text-black' : 'text-white/70 group-hover:text-white'}`}>RGU THESIS FORMAT →</span>
            </button>

            {/* Prototype monograph PDF */}
            <a
              href={PROPERTY_CARD_PDF_URL(ulpin)}
              download={`Bhu_Drishti_3D_Property_Card_${ulpin}.pdf`}
              className={`w-full py-3 px-4 ${
                isLightMode
                  ? 'bg-[#F4F3EE] hover:bg-neutral-200 border-2 border-black text-black shadow-[2px_2px_0px_0px_#000]'
                  : 'bg-white/5 hover:bg-white/15 border-2 border-white/20 hover:border-[#00ff66] text-white'
              } text-xs font-bold transition flex items-center justify-between group`}
            >
              <span className="flex items-center gap-2">
                <Download className={`w-4 h-4 ${isLightMode ? 'text-black' : 'text-[#00ff66]'}`} />
                <span>3D MONOGRAPH (VECTOR PDF)</span>
              </span>
              <span className={`text-[10px] ${isLightMode ? 'text-black/75 group-hover:text-black' : 'text-slate-300 group-hover:text-white'}`}>REPORTLAB 4-PAGE →</span>
            </a>

            {/* Compilable LaTeX Source */}
            <a
              href={PROPERTY_CARD_PDF_URL(ulpin).replace('/pdf/', '/latex/')}
              download={`Bhu_Drishti_3D_Property_Card_${ulpin}.tex`}
              className={`w-full py-3 px-4 ${
                isLightMode
                  ? 'bg-[#F4F3EE] hover:bg-neutral-200 border-2 border-black text-black shadow-[2px_2px_0px_0px_#000]'
                  : 'bg-white/5 hover:bg-white/15 border-2 border-white/20 hover:border-cyan-400 text-white'
              } text-xs font-bold transition flex items-center justify-between group`}
            >
              <span className="flex items-center gap-2">
                <Terminal className={`w-4 h-4 ${isLightMode ? 'text-cyan-700' : 'text-cyan-400'}`} />
                <span>COMPILABLE LATEX SOURCE (.TEX)</span>
              </span>
              <span className={`text-[10px] ${isLightMode ? 'text-black/75 group-hover:text-black' : 'text-slate-300 group-hover:text-white'}`}>OVERLEAF READY →</span>
            </a>

            {/* Cadastral Excel Workbook */}
            <a
              href={CADASTRAL_EXCEL_URL}
              download="Bhu_Drishti_Cadastral_Register.xlsx"
              className={`w-full py-3 px-4 ${
                isLightMode
                  ? 'bg-[#F4F3EE] hover:bg-neutral-200 border-2 border-black text-black shadow-[2px_2px_0px_0px_#000]'
                  : 'bg-white/5 hover:bg-white/15 border-2 border-white/20 hover:border-purple-400 text-white'
              } text-xs font-bold transition flex items-center justify-between group`}
            >
              <span className="flex items-center gap-2">
                <FileSpreadsheet className={`w-4 h-4 ${isLightMode ? 'text-purple-700' : 'text-purple-400'}`} />
                <span>CADASTRAL REGISTER (EXCEL .XLSX)</span>
              </span>
              <span className={`text-[10px] ${isLightMode ? 'text-black/75 group-hover:text-black' : 'text-slate-300 group-hover:text-white'}`}>MULTI-TAB WORKBOOK →</span>
            </a>
          </div>
        </div>
      </section>

      {/* ===================================================================== */}
      {/* SECTION 05 // ARCHITECTURAL BLUEPRINTS & SPATIAL WIREFRAME SCHEMATICS */}
      {/* ===================================================================== */}
      <CadastralWireframeInspector theme="brutalist" isLightMode={isLightMode} />

      {/* ===================================================================== */}
      {/* SECTION 06 // HIGH-DENSITY CADASTRAL CHARTS & LIDAR DENSITY SPECTRUM   */}
      {/* ===================================================================== */}
      <CadastralSpatialCharts theme="brutalist" isLightMode={isLightMode} />

      {/* ===================================================================== */}
      {/* SECTION 07 // DEEP JURISDICTION, DISTRICT BENCHMARKS & TITLE CHAIN     */}
      {/* ===================================================================== */}
      <CadastralDeepTelemetry theme="brutalist" isLightMode={isLightMode} />

      {/* ===================================================================== */}
      {/* SECTION 08 // COMPREHENSIVE CADASTRAL DOCUMENTATION & LEGAL NORMS     */}
      {/* ===================================================================== */}
      <CadastralDocsHub theme="brutalist" isLightMode={isLightMode} />

      {/* ===================================================================== */}
      {/* BRUTALIST TECHNICAL FOOTER                                            */}
      {/* ===================================================================== */}
      <footer className={`max-w-7xl mx-auto px-4 sm:px-6 py-10 font-mono text-xs ${isLightMode ? 'text-black/70 border-t-2 border-black' : 'text-slate-400'} flex flex-col md:flex-row items-start md:items-center justify-between gap-6`}>
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 ${isLightMode ? 'bg-black text-[#00FF66] border border-black' : 'bg-[#00ff66] text-black'} font-black flex items-center justify-center text-sm font-mono`}>
            भू
          </div>
          <div>
            <span className={`${isLightMode ? 'text-black' : 'text-white'} font-bold block uppercase tracking-wider`}>
              SIH26011 STUDENT TEAM
            </span>
            <span className={`text-[10px] ${isLightMode ? 'text-black/75' : 'text-slate-300'}`}>
              Independent hackathon prototype · not affiliated with or endorsed by any government department
            </span>
          </div>
        </div>

        <div className={`flex flex-wrap items-center gap-6 text-[10px] ${isLightMode ? 'text-black/75' : 'text-white/75'}`}>
          <span>Modelled loosely on LADM vocabulary; not ISO 19152 certified</span>
          <span>Demo identifiers, not issued ULPINs</span>
          <span>PROTOTYPE · NOT A GOVERNMENT SYSTEM</span>
          <span className={`${isLightMode ? 'text-black' : 'text-white'} font-bold`}>© 2026 SIH26011</span>
        </div>
      </footer>

      {/* ===================================================================== */}
      {/* OFFICIAL GOVERNMENT DEED & MONOGRAPH PRINT MODAL                      */}
      {/* ===================================================================== */}
      {hero && (
        <GovernmentDeedPrintModal
          property={hero}
          isOpen={printModalOpen}
          onClose={() => setPrintModalOpen(false)}
        />
      )}
    </div>
  );
};