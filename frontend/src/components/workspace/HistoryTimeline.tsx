import React from 'react';
import { HeroProperty } from '../../types/cadastre';
import { AlertTriangle, History } from 'lucide-react';

interface Props {
  property: HeroProperty;
  isEpoch2: boolean;
  onToggleEpoch: (isEpoch2: boolean) => void;
}

export const HistoryTimeline: React.FC<Props> = ({
  property,
  isEpoch2,
  onToggleEpoch,
}) => {
  const epoch2Change = property.epoch2_change;

  return (
    <div className="bg-chalk border-2 border-ink rounded-none p-3.5 text-xs space-y-3 shadow-brutal-sm">
      <div className="flex items-center justify-between pb-2 border-b border-ink">
        <span className="font-bold uppercase tracking-widest text-ink font-display flex items-center gap-1.5">
          <History className="w-3.5 h-3.5 text-accent-strong" />
          <span>Time Slider & Multi-Epoch Survey</span>
        </span>
        <span className="font-mono text-[10px] text-ink-soft font-bold">
          {isEpoch2 ? 'Active: 2027 Survey' : 'Active: 2026 Baseline'}
        </span>
      </div>

      {/* Epoch Switcher Tabs */}
      <div className="grid grid-cols-2 gap-px bg-canvas border-2 border-ink rounded-none p-px overflow-hidden">
        <button
          onClick={() => onToggleEpoch(false)}
          className={`py-1.5 px-2 text-center font-bold transition ${
            !isEpoch2
              ? 'bg-accent text-white shadow-brutal-sm'
              : 'bg-chalk text-ink-soft hover:text-ink'
          }`}
        >
          2026 Epoch 1 (Baseline)
        </button>
        <button
          onClick={() => onToggleEpoch(true)}
          className={`py-1.5 px-2 text-center font-bold transition ${
            isEpoch2
              ? 'bg-amber-500 text-white shadow-brutal-sm'
              : 'bg-chalk text-ink-soft hover:text-ink'
          }`}
        >
          2027 Epoch 2 (Monitoring)
        </button>
      </div>

      {/* Epoch Comparison Details

          This component previously rendered two fixed narratives: an "Approved
          Municipal Sanction Baseline" of 18.0 m / 5 storeys / 1 basement /
          20 flats, and a "Suspected Unauthorized Change Detected" panel
          reporting that "UAV photogrammetry & LiDAR point cloud detected
          vertical expansion above approved sanction envelope (+3.5m, Level 6
          addition)", with a note that a case was "automatically opened in
          reviewer queue in this prototype".

          Every one of those was a literal in the JSX. There is no municipal
          sanction on record, no second observation, no photogrammetry, and no
          case in any queue. Change detection needs two dated observations of
          the same structure from a real source; this deployment has at most
          one, of unknown date. The backend returns epoch2_change: null for
          exactly this reason, and the UI now says so rather than contradicting
          it. */}
      {!epoch2Change ? (
        <div className="p-3 rounded-none bg-canvas border-2 border-ink space-y-2">
          <div className="flex items-center gap-1.5 text-ink-soft font-bold">
            <AlertTriangle className="w-4 h-4 text-ink-soft shrink-0" />
            <span>No comparison available</span>
          </div>
          <p className="text-[11px] text-ink leading-relaxed font-sans">
            Change detection compares two dated observations of the same structure
            from an authoritative source. This deployment holds at most one
            observation, of unknown date, and no sanctioned baseline. There is
            therefore no baseline, no delta, and no finding to report.
          </p>
          <p className="text-[10px] text-ink-soft leading-relaxed font-sans">
            Nothing below is a statement about this property. No municipal
            sanction has been retrieved, no aerial survey has been compared, and
            no enforcement case exists.
          </p>
        </div>
      ) : (
        <div className="p-3 rounded-none bg-amber-50 border-2 border-ink space-y-2 text-amber-950">
          <div className="flex items-center gap-1.5 text-amber-800 font-bold">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>Change detected between two observations</span>
          </div>
          <p className="text-[11px] text-amber-900 leading-relaxed font-sans">
            Height changed by {epoch2Change.delta_height_m}m and
            {' '}{epoch2Change.delta_floors} level(s) were added between
            {' '}{epoch2Change.epoch_from} and {epoch2Change.epoch_to}.
          </p>
          <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-amber-950 bg-chalk/80 p-2.5 rounded-none border-2 border-ink">
            <div>&Delta; Height: <strong>{epoch2Change.delta_height_m}m</strong></div>
            <div>&Delta; Floors: <strong>{epoch2Change.delta_floors}</strong></div>
            <div>Added Units: <strong>{epoch2Change.added_units?.length ?? 0}</strong></div>
            <div>&Delta; Volume: <strong>{epoch2Change.delta_volume_m3} m&sup3;</strong></div>
          </div>
          <div className="pt-2 border-t border-ink text-[10px] text-amber-800 font-bold">
            A difference between two observations is not a finding of
            unauthorised construction, and no authority has been notified.
          </div>
        </div>
      )}
    </div>
  );
};
