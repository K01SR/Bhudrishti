import React, { useState } from 'react';
import { HeroProperty, CadastralUnit } from '../../types/cadastre';
import { ChevronDown, ChevronRight, Building2, Layers, Home, MapPin } from 'lucide-react';

interface Props {
  property: HeroProperty;
  selectedUnit: CadastralUnit | null;
  onSelectUnit: (unit: CadastralUnit | null) => void;
}

export const HierarchyTree: React.FC<Props> = ({
  property,
  selectedUnit,
  onSelectUnit,
}) => {
  const [expandedLevels, setExpandedLevels] = useState<Record<string, boolean>>({
    B1: true,
    G: false,
    L01: false,
    L02: true, // Flat 201 Hero Case
    L03: false,
    L04: false,
  });

  const toggleLevel = (lvl: string) => {
    setExpandedLevels((prev) => ({ ...prev, [lvl]: !prev[lvl] }));
  };

  return (
    <div className="bg-chalk border-2 border-ink rounded-none p-3.5 text-xs shadow-brutal-sm">
      <div className="flex items-center gap-1.5 font-bold uppercase tracking-widest text-ink pb-2.5 mb-2.5 border-b border-ink">
        <MapPin className="w-3.5 h-3.5 text-accent-strong" />
        <span>Cadastral Hierarchy Tree</span>
      </div>

      <div className="space-y-1.5">
        {/* Administrative Path */}
        <div className="text-[11px] text-ink-mut font-mono pl-1">
          MH / Thane / Thane / Ward 08
        </div>

        {/* Parcel Node */}
        <div className="flex items-center gap-1.5 py-1 text-ink font-bold">
          <ChevronDown className="w-3 h-3 text-ink-mut" />
          <span className="font-mono text-accent-strong font-bold">
            Parcel {property.parcel.survey_number ?? property.parcel.ulpin}
          </span>
          <span className="text-[10px] text-ink-mut font-mono">
            {property.parcel.document_area_m2 != null ? `(${property.parcel.document_area_m2} m²)` : '(area not stated)'}
          </span>
        </div>

        {/* Building Node */}
        <div className="pl-4 space-y-1">
          <div className="flex items-center gap-1.5 py-1 text-ink font-bold">
            <Building2 className="w-3.5 h-3.5 text-emerald-600" />
            <span>Building {property.structure.building_code ?? 'unnamed'}</span>
            <span className="text-[10px] text-ink-soft font-mono font-normal">
              {/*
                The "5F + 1B" here was a literal, so every record in the tree
                claimed five floors and a basement whatever it said. Both now
                come from the record, and state nothing when unstated.
              */}
              ({property.structure.height_m != null ? `${property.structure.height_m}m` : 'height not stated'}
              {property.structure.floors_count != null ? ` | ${property.structure.floors_count}F` : ''}
              {property.structure.basements_count != null && property.structure.basements_count > 0
                ? ` + ${property.structure.basements_count}B`
                : ''})
            </span>
          </div>

          {/* Levels & Strata Units */}
          <div className="pl-4 space-y-1">
            {property.levels.map((lvl, lvlIdx) => {
              // A level with no code is still a row, so the fallback key is
              // positional rather than a fabricated 'L01'.
              const levelKey = lvl.level_code ?? `#${lvlIdx}`;
              const isExpanded = expandedLevels[levelKey];
              const levelUnits = property.units.filter((u) => u.level_code === lvl.level_code);

              return (
                <div key={levelKey} className="space-y-0.5">
                  {/* Level Header */}
                  <div
                    onClick={() => toggleLevel(levelKey)}
                    className="flex items-center justify-between py-1 px-2 rounded-none hover:bg-canvas cursor-pointer text-ink font-bold transition"
                  >
                    <div className="flex items-center gap-1.5">
                      {isExpanded ? (
                        <ChevronDown className="w-3 h-3 text-ink-mut" />
                      ) : (
                        <ChevronRight className="w-3 h-3 text-ink-mut" />
                      )}
                      <Layers className="w-3 h-3 text-accent-strong" />
                      {/* An unnamed level is not "Ground Floor". */}
                      <span>{lvl.name ?? (lvl.level_code ?? 'Unnamed level')}</span>
                    </div>
                    <span className="font-mono text-[10px] text-ink-mut">
                      {lvl.min_z != null && lvl.max_z != null
                        ? `[${lvl.min_z.toFixed(1)}m, ${lvl.max_z.toFixed(1)}m]`
                        : '[elevation not stated]'}
                    </span>
                  </div>

                  {/* Units inside this level */}
                  {isExpanded && (
                    <div className="pl-5 space-y-0.5 mt-0.5">
                      {levelUnits.map((u) => {
                        const isSelected = selectedUnit?.unit_number === u.unit_number;
                        const hasMortgage = u.rights?.some((r) => r.right_type === 'MORTGAGE');

                        return (
                          <div
                            key={u.unit_number}
                            onClick={() => onSelectUnit(isSelected ? null : u)}
                            className={`flex items-center justify-between py-1 px-2.5 rounded-none cursor-pointer transition ${
                              isSelected
                                ? 'bg-accent-faint text-ink border-2 border-ink font-bold shadow-brutal-sm'
                                : 'text-ink-soft hover:text-ink hover:bg-canvas'
                            }`}
                          >
                            <div className="flex items-center gap-1.5">
                              <Home className="w-3 h-3 text-ink-mut" />
                              <span className="font-bold text-ink">
                                Unit {u.unit_number}
                              </span>
                              {hasMortgage && (
                                <span className="text-[9px] font-bold text-red-700 bg-red-50 border-2 border-ink px-1 py-0.2 rounded-none">
                                  MORTGAGE
                                </span>
                              )}
                            </div>
                            <span className="font-mono text-[10px] text-ink-mut">
                              {u.volume_m3.toFixed(0)} m³
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
