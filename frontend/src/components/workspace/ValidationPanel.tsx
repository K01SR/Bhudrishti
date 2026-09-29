import React from 'react';
import { ValidationSummary, TopologyIssue } from '../../types/cadastre';
import { CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';

interface Props {
  /** Null when no validation run is on record for this parcel. */
  validation: ValidationSummary | null;
  onSelectIssue?: (issue: TopologyIssue) => void;
}

export const ValidationPanel: React.FC<Props> = ({
  validation,
  onSelectIssue,
}) => {
  // No run means no verdict. This previously only ever received a summary
  // because the caller invented one, so the empty state below is the first
  // time this component has had to answer for itself.
  if (!validation) {
    return (
      <div className="bg-chalk border-2 border-ink rounded-none p-3.5 text-xs">
        <span className="font-bold uppercase tracking-widest text-ink">
          Topology &amp; Spatial QA
        </span>
        <p className="text-ink-mut mt-2">
          No validation run is on record for this parcel. Nothing has been
          checked, so there is no pass count and no verdict to show.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-chalk border-2 border-ink rounded-none p-3.5 text-xs shadow-brutal-sm">
      <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-ink">
        <span className="font-bold uppercase tracking-widest text-ink">
          Topology & Spatial QA (R001–R016)
        </span>
        <div className="flex items-center gap-1.5 font-mono text-[10px]">
          <span className="text-emerald-700 bg-emerald-50 border-2 border-ink px-2 py-0.5 rounded-none font-bold">
            {validation.passed_rules} Passed
          </span>
          {validation.failed_rules > 0 && (
            <span className="text-red-700 bg-red-50 border-2 border-ink px-2 py-0.5 rounded-none font-bold animate-pulse">
              {validation.failed_rules} Clash
            </span>
          )}
        </div>
      </div>

      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
        {validation.findings.map((issue) => {
          const isFail = issue.status === 'FAIL';
          const isWarning = issue.status === 'WARNING';

          return (
            <div
              key={issue.rule_id}
              onClick={() => onSelectIssue && onSelectIssue(issue)}
              className={`p-2.5 rounded-none border-2 cursor-pointer transition ${
                isFail
                  ? 'bg-red-50/90 border-ink text-red-950 shadow-brutal-sm'
                  : isWarning
                  ? 'bg-amber-50/90 border-ink text-amber-950'
                  : 'bg-canvas border-ink hover:bg-canvas text-ink'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="font-mono font-bold text-[11px] text-accent-strong bg-chalk px-1.5 py-0.5 rounded-none border-2 border-ink">
                    {issue.rule_id}
                  </span>
                  <span className="font-bold">{issue.rule_name}</span>
                </div>
                {isFail ? (
                  <span className="flex items-center gap-1 text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded-none border-2 border-ink">
                    <XCircle className="w-3 h-3" />
                    FAIL
                  </span>
                ) : isWarning ? (
                  <span className="flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded-none border-2 border-ink">
                    <AlertTriangle className="w-3 h-3" />
                    WARN
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-700">
                    <CheckCircle2 className="w-3 h-3" />
                    PASS
                  </span>
                )}
              </div>

              <p className="mt-1.5 text-[11px] text-ink-soft leading-relaxed font-sans">
                {issue.message}
              </p>

              {issue.recommended_action && (
                <div className="mt-2 text-[10px] font-bold text-amber-900 bg-amber-100/70 p-2 rounded-none border-2 border-ink">
                  Recommendation: {issue.recommended_action}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
