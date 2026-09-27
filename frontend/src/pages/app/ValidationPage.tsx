import React, { useEffect, useState } from 'react';
import { Scale, ShieldAlert, Timer, Database, Palette, Download, X, Copy, Check } from 'lucide-react';
import { fetchRulesCatalogue, fetchHeroProperty, fetchCanonicalSchema, fetchRightsColorModes } from '../../services/api';
import { Card, SeverityBadge, StatusBadge, Skeleton, DemoHint, Button } from '../../components/ui';

type Rule = { rule_id: string; name: string; severity: string; description?: string };

export const ValidationPage: React.FC = () => {
  const [rules, setRules] = useState<Rule[]>([]);
  const [heroValidation, setHeroValidation] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  // Schema & Color Modes Modal States
  const [schemaModalOpen, setSchemaModalOpen] = useState(false);
  const [schemaData, setSchemaData] = useState<any | null>(null);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [copiedSchema, setCopiedSchema] = useState(false);

  const [colorModesOpen, setColorModesOpen] = useState(false);
  const [colorModes, setColorModes] = useState<any[]>([]);
  const [loadingColorModes, setLoadingColorModes] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([fetchRulesCatalogue(), fetchHeroProperty().catch(() => null)])
      .then(([r, h]) => {
        if (!active) return;
        setRules((r as Rule[]) || []);
        setHeroValidation(h?.validation || null);
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const handleOpenSchema = async () => {
    setSchemaModalOpen(true);
    if (!schemaData) {
      setLoadingSchema(true);
      try {
        const s = await fetchCanonicalSchema();
        setSchemaData(s);
      } catch (e) {
        console.error('Failed to fetch canonical schema', e);
      } finally {
        setLoadingSchema(false);
      }
    }
  };

  const handleOpenColorModes = async () => {
    setColorModesOpen(true);
    if (colorModes.length === 0) {
      setLoadingColorModes(true);
      try {
        const res = await fetchRightsColorModes();
        setColorModes(res.modes || []);
      } catch (e) {
        console.error('Failed to fetch color modes', e);
      } finally {
        setLoadingColorModes(false);
      }
    }
  };

  const handleCopySchema = () => {
    if (!schemaData) return;
    navigator.clipboard.writeText(JSON.stringify(schemaData, null, 2));
    setCopiedSchema(true);
    setTimeout(() => setCopiedSchema(false), 2000);
  };

  const severityOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
  const sorted = [...rules].sort((a, b) => (severityOrder[a.severity as keyof typeof severityOrder] ?? 9) - (severityOrder[b.severity as keyof typeof severityOrder] ?? 9));

  return (
    <div className="flex flex-col gap-5 animate-rise-in">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 annotation text-accent-strong">
            <span className="text-accent-strong">Reviewer (demo)</span><span>/</span><span>Validation</span>
          </div>
          <h1 className="text-2xl font-black text-ink font-display tracking-tight mt-1">Spatial QA Rules Engine</h1>
          <p className="text-sm text-ink-soft mt-1">
            Twelve topology and spatial-QA rules validate every 3D submission against governing cadastral reference
            standards before records reach approval.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleOpenSchema}
            className="flex items-center gap-1.5"
          >
            <Database className="w-3.5 h-3.5 text-accent-strong" />
            LADM ISO 19152 Schema
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleOpenColorModes}
            className="flex items-center gap-1.5"
          >
            <Palette className="w-3.5 h-3.5 text-accent-strong" />
            3D Color Modes & Legends
          </Button>
        </div>
      </div>

      {heroValidation && (
        <Card className="p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="w-10 h-10 rounded-none bg-emerald-50 border-2 border-ink flex items-center justify-center">
                <Scale className="w-5 h-5 text-emerald-600" />
              </span>
              <div>
                <div className="text-xs font-bold text-ink">Last run on Building B-17</div>
                <div className="text-[11px] text-ink-soft">{heroValidation.total_rules} rules · {heroValidation.passed_rules} passed · {heroValidation.failed_rules} failed · {heroValidation.warning_rules} warnings</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={heroValidation.overall_status} />
              <DemoHint />
            </div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {loading
          ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-none" />)
          : sorted.map((r) => (
              <Card key={r.rule_id} className="p-4 flex items-start gap-3">
                <code className="font-mono text-[11px] font-black text-accent-strong bg-accent-faint border-2 border-ink px-1.5 py-0.5 rounded-none shrink-0">{r.rule_id}</code>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-ink">{r.name}</span>
                    <SeverityBadge severity={r.severity} />
                  </div>
                  {r.description && <p className="text-[11px] text-ink-soft mt-1 leading-relaxed">{r.description}</p>}
                </div>
              </Card>
            ))}
      </div>

      <div className="p-4 rounded-none bg-amber-50/70 border-2 border-ink text-xs text-amber-800 flex items-start gap-2.5">
        <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <span>
          <strong>Why it matters:</strong> R009 (subsurface clash) is live-failing for B-17 against the stormwater drain
          at Z=−3.2 m — a real rejection gate that a builder must resolve before approval.
        </span>
      </div>

      <div className="flex items-center gap-2 text-[11px] text-ink-soft">
        <Timer className="w-3.5 h-3.5 text-ink-mut" />
        Rules engine executes in-process over the deterministic pilot dataset. Results are reproducible every run.
      </div>

      {/* LADM ISO 19152 Schema Modal */}
      {schemaModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-rise-in">
          <div className="bg-white rounded-none max-w-2xl w-full border-2 border-ink shadow-brutal-xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="p-4 border-b border-ink flex items-center justify-between bg-canvas">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-accent-strong" />
                <h3 className="font-bold text-sm text-ink font-display">LADM ISO 19152 (Part 3: 3D Cadastre) Schema</h3>
              </div>
              <button
                onClick={() => setSchemaModalOpen(false)}
                className="p-1 text-ink-soft hover:text-ink rounded-none"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 font-mono text-xs text-ink bg-slate-900 text-ink-mut">
              {loadingSchema ? (
                <div className="py-8 text-center text-ink-soft">Loading canonical schema...</div>
              ) : (
                <pre className="whitespace-pre-wrap">{JSON.stringify(schemaData, null, 2)}</pre>
              )}
            </div>

            <div className="p-3 border-t border-ink flex items-center justify-between bg-canvas text-xs">
              <span className="text-[11px] text-ink-soft">Endpoint: GET /api/v1/properties/canonical-schema</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCopySchema}
                  className="flex items-center gap-1 text-xs"
                >
                  {copiedSchema ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedSchema ? 'Copied' : 'Copy JSON'}
                </Button>
                <a
                  href={`data:text/json;charset=utf-8,${encodeURIComponent(JSON.stringify(schemaData, null, 2))}`}
                  download="LADM_ISO_19152_Schema.json"
                  className="px-3 py-1.5 bg-ink hover:bg-ink text-white rounded-none text-xs font-bold transition flex items-center gap-1"
                >
                  <Download className="w-3.5 h-3.5" /> Download
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 3D Viewer Color Schemes & Legends Modal */}
      {colorModesOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-rise-in">
          <div className="bg-white rounded-none max-w-2xl w-full border-2 border-ink shadow-brutal-xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="p-4 border-b border-ink flex items-center justify-between bg-canvas">
              <div className="flex items-center gap-2">
                <Palette className="w-4 h-4 text-accent-strong" />
                <h3 className="font-bold text-sm text-ink font-display">3D Viewer Color Schemes & Statutory Taxonomies</h3>
              </div>
              <button
                onClick={() => setColorModesOpen(false)}
                className="p-1 text-ink-soft hover:text-ink rounded-none"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 overflow-y-auto flex-1 space-y-4">
              {loadingColorModes ? (
                <div className="py-8 text-center text-ink-soft">Loading color taxonomies...</div>
              ) : (
                colorModes.map((m: any) => (
                  <div key={m.id} className="p-3.5 rounded-none border-2 border-ink bg-canvas space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-ink">{m.label}</span>
                      <code className="text-[10px] font-mono text-accent-strong bg-accent-faint px-1.5 py-0.5 rounded-none">
                        mode: {m.id}
                      </code>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                      {m.legend?.map((item: any, idx: number) => (
                        <div key={idx} className="flex items-center gap-2.5 text-xs">
                          <span
                            className="w-3.5 h-3.5 rounded-none shrink-0 shadow-brutal-sm border-2 border-black/10"
                            style={{ backgroundColor: item.color }}
                          />
                          <span className="text-ink">{item.label}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="p-3 border-t border-ink flex items-center justify-between bg-canvas text-xs">
              <span className="text-[11px] text-ink-soft">Endpoint: GET /api/v1/rights/color-modes</span>
              <Button variant="secondary" size="sm" onClick={() => setColorModesOpen(false)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};