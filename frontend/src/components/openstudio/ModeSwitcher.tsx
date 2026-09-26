import React from 'react';
import { Layers, Box, EyeOff } from 'lucide-react';
import { MapMode, useOpenStudioStore } from '../../store/useOpenStudioStore';

const MODES: { id: MapMode; label: string; icon: React.ReactNode }[] = [
  { id: 'SURFACE', label: '2D Surface', icon: <Layers className="w-3.5 h-3.5" /> },
  { id: '3D', label: '3D Extruded', icon: <Box className="w-3.5 h-3.5" /> },
  { id: 'UNDERGROUND', label: 'Underground', icon: <EyeOff className="w-3.5 h-3.5" /> },
];

export const ModeSwitcher: React.FC = () => {
  const mapMode = useOpenStudioStore((s) => s.mapMode);
  const setMapMode = useOpenStudioStore((s) => s.setMapMode);

  return (
    <div className="flex items-center p-0.5 rounded-none border border-slate-700/80 bg-slate-900/95 backdrop-blur-md shadow-brutal-lg overflow-hidden">
      {MODES.map((m) => {
        const active = mapMode === m.id;
        return (
          <button
            key={m.id}
            onClick={() => setMapMode(m.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-bold tracking-wide transition-all ${
              active
                ? 'bg-accent text-white font-bold'
                : 'text-slate-300 hover:text-slate-300 hover:bg-slate-800/60'
            }`}
          >
            {m.icon}
            <span>{m.label}</span>
          </button>
        );
      })}
    </div>
  );
};
