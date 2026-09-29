import React from 'react';
import { HeroProperty, CadastralUnit } from '../../types/cadastre';
import { Palette, EyeOff } from 'lucide-react';
import { useApp } from '../../context/AppContext';

interface Props {
  property: HeroProperty;
  selectedUnit: CadastralUnit | null;
  activeColorMode: string;
  onColorModeChange: (mode: string) => void;
}

export const RightsPanel: React.FC<Props> = ({
  property,
  selectedUnit,
  activeColorMode,
  onColorModeChange,
}) => {
  const { permissions } = useApp();
  const canViewSensitive = permissions.canViewSensitive;

  // Unit 201 Hero Case
  const heroUnit = selectedUnit || property.units.find((u) => u.unit_number === '201') || property.units[0];
  const rights = heroUnit?.rights || [];

  const redactParty = (name: string) => (canViewSensitive ? name : '••••••••');
  const redactAmount = (amount: number) => (canViewSensitive ? `₹ ${amount.toLocaleString('en-IN')}` : '₹ ••••••');

  const colorModes = [
    { id: 'verification', label: 'Verification Status' },
    { id: 'rights', label: 'Rights & Mortgages' },
    { id: 'type', label: 'Spatial Type' },
    { id: 'conflict', label: 'QA Conflicts' },
  ];

  return (
    <div className="bg-chalk border-2 border-ink rounded-none p-3.5 text-xs space-y-3.5 shadow-brutal-sm">
      {/* 3D Color Mode Selector */}
      <div>
        <div className="flex items-center gap-1.5 font-bold uppercase tracking-widest text-ink pb-2 mb-2 border-b border-ink">
          <Palette className="w-3.5 h-3.5 text-accent-strong" />
          <span>3D View Color Mode</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {colorModes.map((m) => (
            <button
              key={m.id}
              onClick={() => onColorModeChange(m.id)}
              className={`px-2.5 py-1.5 rounded-none text-[11px] font-bold text-left transition ${
                activeColorMode === m.id
                  ? 'bg-accent text-white shadow-brutal-sm'
                  : 'bg-canvas text-ink hover:bg-canvas'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {!canViewSensitive && (
        <div className="flex items-center gap-2 px-2.5 py-2 rounded-none bg-amber-50 border-2 border-ink text-amber-800 text-[10px] font-bold">
          <EyeOff className="w-3.5 h-3.5 shrink-0" />
          Party names and mortgage amounts redacted under DPDP Act 2023 — your role does not have rights to
          sensitive ownership data.
        </div>
      )}

      {/* Rights & Encumbrances Breakdown */}
      <div>
        <div className="flex items-center justify-between pb-2 mb-2 border-b border-ink">
          <span className="font-bold uppercase tracking-widest text-ink">
            Rights on Flat {heroUnit?.unit_number}
          </span>
          <span className="text-[10px] text-ink-mut font-mono">
            {rights.length} Registered Encumbrances
          </span>
        </div>

        <div className="space-y-2">
          {rights.map((r, i) => (
            <div
              key={i}
              className="p-2.5 rounded-none bg-canvas border-2 border-ink space-y-1.5 text-[11px]"
            >
              <div className="flex items-center justify-between">
                <span
                  className="font-bold text-[10px] px-2 py-0.5 rounded-none"
                  style={{
                    backgroundColor: `${r.color_hex || '#2563eb'}15`,
                    color: r.color_hex || '#2563eb',
                  }}
                >
                  {r.right_type}
                </span>
                <span className="font-mono text-[10px] font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded-none border-2 border-ink">
                  {r.encumbrance_status}
                </span>
              </div>

              <div className="font-bold text-ink font-mono tracking-widest">{redactParty(r.party_name)}</div>

              {r.mortgage_amount_inr && (
                <div className="flex justify-between text-ink-soft font-mono text-[10px] pt-1 border-t border-ink">
                  <span>Principal Lien:</span>
                  <span className={canViewSensitive ? 'text-red-700 font-bold' : 'text-ink-soft font-bold'}>
                    {redactAmount(r.mortgage_amount_inr)}
                  </span>
                </div>
              )}

              {r.easement_purpose && (
                <div className="text-[10px] text-ink-soft font-sans leading-tight pt-1 border-t border-ink">
                  Purpose: {redactParty(r.easement_purpose)}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="mt-2 text-[10px] text-ink-mut italic">
          Disclaimer: Synthetic demo party names and loan liens for technical evaluation.
        </div>
      </div>
    </div>
  );
};
