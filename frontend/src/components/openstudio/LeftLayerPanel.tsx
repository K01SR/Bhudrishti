import React from 'react';
import {
  Layers,
  Building2,
  Map as MapIcon,
  Navigation,
  Compass,
  Zap,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  Palette,
  Eye,
  EyeOff,
  Globe2,
  Mountain,
  Satellite,
} from 'lucide-react';
import { useOpenStudioStore, ColorMode } from '../../store/useOpenStudioStore';

export const LeftLayerPanel: React.FC = () => {
  const {
    leftPanelOpen,
    setLeftPanelOpen,
    layers,
    toggleLayer,
    colorMode,
    setColorMode,
  } = useOpenStudioStore();

  /**
   * `connected: false` means the toggle has no data behind it in this view.
   *
   * Five of these used to render as ordinary switches over sources they never
   * fetched: a "State Cadastre API" and a "Municipal GPR Survey" that supplied
   * nothing, behind a confident on/off. A switch that cannot change the map is
   * worse than an absent one, because it reports a capability the view does not
   * have. They now say so and are inert rather than lying.
   */
  const layerItems = [
    {
      key: 'buildings3D' as const,
      label: '3D Building Extrusions',
      source: 'OSM Overpass Live',
      icon: <Building2 className="w-3.5 h-3.5 text-slate-300" />,
      active: layers.buildings3D,
      connected: true,
    },
    {
      key: 'landParcels' as const,
      label: 'Cadastral Land Parcels',
      source: 'Not connected in this view',
      icon: <MapIcon className="w-3.5 h-3.5 text-slate-500" />,
      active: layers.landParcels,
      connected: false,
    },
    {
      key: 'roadNetwork' as const,
      label: 'Highways & Arterial Roads',
      source: 'OSM Highway Graph',
      icon: <Navigation className="w-3.5 h-3.5 text-emerald-400" />,
      active: layers.roadNetwork,
      connected: true,
    },
    {
      key: 'civicAmenities' as const,
      label: 'Civic Amenities & Metro',
      source: 'OSM Overpass Live',
      icon: <Compass className="w-3.5 h-3.5 text-slate-300" />,
      active: layers.civicAmenities,
      connected: true,
    },
    {
      key: 'localityLabels' as const,
      label: 'Locality & Ward Labels',
      // This was 'not drawn in this view': the label query fired on every
      // viewport change and the result was discarded, so it cost a network
      // round-trip and drew nothing. It is now fetched and rendered in this
      // view, alongside the amenities, in one debounced call per viewport
      // change rather than one each.
      source: 'OSM Overpass Live',
      icon: <Globe2 className="w-3.5 h-3.5 text-slate-300" />,
      active: layers.localityLabels,
      connected: true,
    },
    {
      key: 'subsurfacePipes' as const,
      label: 'Subsurface Utilities (3D Pipes)',
      // Was 'Municipal GPR Survey'. The geometry was two hardcoded line
      // segments and no survey was ever consulted, so the credit named a source
      // that supplied nothing. It is now the truth: derived from OSM roads.
      source: 'Prototype — derived from OSM roads',
      icon: <Zap className="w-3.5 h-3.5 text-rose-400" />,
      active: layers.subsurfacePipes,
      connected: true,
    },
    {
      key: 'officialCadastre' as const,
      label: 'Official 3D Twins (Pilot)',
      source: 'Not connected in this view',
      icon: <ShieldCheck className="w-3.5 h-3.5 text-slate-500" />,
      active: layers.officialCadastre,
      connected: false,
    },
    {
      key: 'terrainRelief' as const,
      label: 'Terrain Relief',
      source: 'AWS Terrain Tiles',
      icon: <Mountain className="w-3.5 h-3.5 text-slate-300" />,
      active: layers.terrainRelief,
      connected: true,
    },
    {
      key: 'satelliteImagery' as const,
      label: 'Satellite Imagery',
      source: 'Sentinel-2 cloudless (EOX)',
      icon: <Satellite className="w-3.5 h-3.5 text-sky-400" />,
      active: layers.satelliteImagery,
      connected: true,
    },
  ];

  // The count in the header is of layers that can actually change the map.
  // Counting inert switches toward it overstated what the view was showing.
  const connectedItems = layerItems.filter((l) => l.connected);

  return (
    <aside
      className={`relative z-20 flex flex-col border-r border-white/40 bg-slate-950/95 backdrop-blur-xl transition-all duration-300 ease-in-out ${
        leftPanelOpen ? 'w-72' : 'w-12'
      } h-full select-none`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-slate-800/90 min-h-[52px]">
        {leftPanelOpen && (
          <div className="flex items-center gap-2 overflow-hidden">
            <Layers className="w-4 h-4 text-slate-300 flex-shrink-0" />
            <span className="text-xs font-bold tracking-widest uppercase text-slate-300 truncate">
              Spatial Layers
            </span>
          </div>
        )}
        <button
          onClick={() => setLeftPanelOpen(!leftPanelOpen)}
          className="p-1 rounded-none text-slate-300 hover:text-white hover:bg-slate-800/80 transition ml-auto"
          title={leftPanelOpen ? 'Collapse Layer Panel' : 'Expand Layer Panel'}
        >
          {leftPanelOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
      </div>

      {/* Panel Content */}
      {leftPanelOpen ? (
        <div className="flex-1 overflow-y-auto p-3 space-y-4 text-xs font-sans">
          {/* Thematic 3D Color Mode Section */}
          <div className="space-y-2 bg-slate-900/60 p-2.5 rounded-none border border-white/40">
            <div className="flex items-center justify-between text-[11px] font-bold text-slate-300">
              <span className="flex items-center gap-1.5">
                <Palette className="w-3.5 h-3.5 text-slate-300" /> 3D Extrusion Color Mode:
              </span>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {(
                [
                  { id: 'height', label: 'Elevation' },
                  { id: 'landuse', label: 'Zoning' },
                  { id: 'fsi', label: 'FSI / Risk' },
                  { id: 'lineage', label: 'Lineage' },
                ] as { id: ColorMode; label: string }[]
              ).map((mode) => (
                <button
                  key={mode.id}
                  onClick={() => setColorMode(mode.id)}
                  className={`py-1.5 px-2 rounded-none text-[10px] font-mono font-bold uppercase transition ${
                    colorMode === mode.id
                      ? 'bg-accent text-white'
                      : 'bg-slate-800/80 text-slate-300 hover:text-slate-300'
                  }`}
                >
                  {mode.label}
                </button>
              ))}
            </div>
          </div>

          {/* Active Layer Toggles */}
          <div className="space-y-1">
            <span className="text-[10px] uppercase font-bold tracking-widest text-slate-300 px-1">
              Active Map Layers ({connectedItems.filter((l) => l.active).length}/{connectedItems.length})
            </span>
            <div className="space-y-1 pt-1">
              {layerItems.map((item) => (
                <button
                  key={item.key}
                  onClick={() => {
                    if (!item.connected) return;
                    toggleLayer(item.key);
                  }}
                  disabled={!item.connected}
                  title={
                    item.connected
                      ? item.source
                      : `${item.label} has no data source wired up in this view. Available in the 2D cadastral map.`
                  }
                  aria-disabled={!item.connected}
                  className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-none transition text-left border ${
                    !item.connected
                      ? 'bg-slate-950/30 border-ink/60 text-slate-500 cursor-not-allowed opacity-60'
                      : item.active
                        ? 'bg-slate-900/90 border-slate-700/80 text-slate-300 hover:border-accent/50'
                        : 'bg-slate-950/40 border-ink text-slate-300 hover:bg-slate-900/40'
                  }`}
                >
                  <span className="flex-shrink-0">{item.icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-bold leading-tight truncate">{item.label}</div>
                    <div className="text-[9px] font-mono text-slate-300 truncate mt-0.5">{item.source}</div>
                  </div>
                  <span className="flex-shrink-0 text-slate-300">
                    {!item.connected ? (
                      <EyeOff className="w-3.5 h-3.5 text-slate-500" />
                    ) : item.active ? (
                      <Eye className="w-3.5 h-3.5 text-slate-300" />
                    ) : (
                      <EyeOff className="w-3.5 h-3.5 text-slate-300" />
                    )}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Provenance Box */}
          <div className="p-2.5 rounded-none bg-slate-900/40 border border-white/40 text-[10px] text-slate-300 space-y-1 font-mono">
            <div className="flex items-center gap-1.5 text-emerald-400 font-bold uppercase">
              <ShieldCheck className="w-3 h-3" /> Real-time Open Cadastre
            </div>
            <div>Overpass Turbo Query · Level 2+ GeoJSON</div>
            <div className="text-slate-300">Bounding Box: Dynamic Viewport</div>
          </div>
        </div>
      ) : (
        /* Collapsed Icon Bar */
        <div className="py-2 flex flex-col items-center gap-3 text-slate-300">
          <Building2 className="w-4 h-4 text-slate-300" />
          <MapIcon className="w-4 h-4 text-slate-300" />
          <Navigation className="w-4 h-4 text-emerald-400" />
          <Zap className="w-4 h-4 text-rose-400" />
        </div>
      )}
    </aside>
  );
};
