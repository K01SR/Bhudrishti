import React, { useState } from 'react';
import { EvidenceStream } from '../../types/cadastre';
import { CheckCircle2, AlertCircle, FileCode, Satellite, Camera, Crosshair, Map } from 'lucide-react';

interface Props {
  evidenceStreams: EvidenceStream[];
}

export const EvidencePanel: React.FC<Props> = ({ evidenceStreams }) => {
  const [selectedStream, setSelectedStream] = useState<EvidenceStream | null>(null);

  const getSourceIcon = (type: string) => {
    if (type.includes('GIS')) return Map;
    if (type.includes('DRONE')) return Camera;
    if (type.includes('LIDAR')) return Satellite;
    if (type.includes('FLOOR')) return FileCode;
    return Crosshair;
  };

  return (
    <div className="bg-chalk border-2 border-ink rounded-none p-3.5 text-xs shadow-brutal-sm">
      <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-ink">
        <span className="font-bold uppercase tracking-widest text-ink">
          Multi-Source Evidence (6 Streams)
        </span>
        <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 border-2 border-ink px-2 py-0.5 rounded-none">
          Completeness: High
        </span>
      </div>

      <div className="space-y-2">
        {evidenceStreams.map((s) => {
          const Icon = getSourceIcon(s.source_type);
          const isSelected = selectedStream?.id === s.id;

          return (
            <div
              key={s.id}
              onClick={() => setSelectedStream(isSelected ? null : s)}
              className={`p-2.5 rounded-none border-2 cursor-pointer transition ${
                isSelected
                  ? 'bg-accent-faint border-ink text-ink shadow-brutal-sm'
                  : 'bg-canvas border-ink hover:bg-canvas text-ink'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-none bg-accent/70 text-accent-strong flex items-center justify-center shrink-0">
                    <Icon className="w-3.5 h-3.5" />
                  </div>
                  <span className="font-bold">{s.name}</span>
                </div>
                {/*
                  Was keyed on quality_result containing "FLAGGED", so any stream
                  whose quality string did not contain that word was labelled
                  "Available" in green. None of them are: the API reports
                  available: false for all seven. It now reads that field.
                */}
                {s.available ? (
                  <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-700">
                    <CheckCircle2 className="w-3 h-3" />
                    Available
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-50 border-2 border-ink px-1.5 py-0.5 rounded-none">
                    <AlertCircle className="w-3 h-3" />
                    NOT SOURCED
                  </span>
                )}
              </div>

              <div className="flex items-center justify-between mt-1.5 text-[10px] text-ink-soft font-mono">
                <span>{s.id}</span>
                <span>tier: {s.confidence_tier}</span>
              </div>

              {/* Expanded Provenance Details */}
              {isSelected && (
                <div className="mt-2.5 pt-2.5 border-t border-ink space-y-1.5 text-[11px] font-mono text-ink bg-chalk p-2.5 rounded-none">
                  <div className="flex justify-between">
                    <span className="text-ink-mut font-sans">Format:</span>
                    <span className="font-bold">{s.format || 'not specified'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink-mut font-sans">CRS:</span>
                    <span className="font-bold">{s.crs || 'not established'}</span>
                  </div>
                  {/*
                    The "File Name" and "SHA-256 Hash" rows rendered
                    s.file_name and s.file_hash, neither of which the API ever
                    returns. They displayed as empty cells under a hash heading,
                    which is worse than showing nothing: it implies a file was
                    received and hashed when no file exists. Replaced with the
                    provenance statement the API does send.
                  */}
                  <div className="flex flex-col">
                    <span className="text-ink-mut font-sans">Provenance:</span>
                    <span className="text-[10px] text-ink-soft">{s.provenance}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-ink-mut font-sans">To activate:</span>
                    <span className="text-[10px] text-ink-soft">{s.required_to_activate}</span>
                  </div>
                  <div className="mt-1.5 pt-1.5 border-t border-ink text-[10px] text-ink font-sans">
                    {s.quality_result}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
