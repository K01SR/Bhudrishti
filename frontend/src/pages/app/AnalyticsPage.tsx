import React, { useEffect, useState } from 'react';
import { Clock, Zap, LineChart, Coins, FileText, Shield } from 'lucide-react';
import { Link } from 'react-router-dom';
import { fetchMetrics, fetchJurisdictionSummary, fetchHeroProperty, fetchRevenueRecovery } from '../../services/api';
import { RevenueRecoveryResponse } from '../../types/cadastre';
import { Card, Badge, Skeleton, DemoHint } from '../../components/ui';
import { cn } from '../../lib/cn';
import { DemandNoticeModal } from '../../components/modals/DemandNoticeModal';
import { BuyerShieldModal } from '../../components/modals/BuyerShieldModal';

export const AnalyticsPage: React.FC = () => {
  const [metrics, setMetrics] = useState<any | null>(null);
  const [summary, setSummary] = useState<any | null>(null);
  const [benchmarks, setBenchmarks] = useState<any | null>(null);
  const [revenueRecovery, setRevenueRecovery] = useState<RevenueRecoveryResponse | null>(null);
  const [noticeBuilding, setNoticeBuilding] = useState<string | null>(null);
  const [buyerShieldTarget, setBuyerShieldTarget] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchMetrics().catch(() => null),
      fetchJurisdictionSummary().catch(() => null),
      fetchHeroProperty().catch(() => null).then((h) => h?.validation || null),
      fetch('/api/v1/pipelines/benchmarks').then((r) => r.json()).catch(() => null),
      fetchRevenueRecovery().catch(() => null),
    ])
      .then(([m, s, qa, b, rev]) => {
        if (!active) return;
        if (m) setMetrics(m);
        if (s) setSummary(s);
        if (qa) setTopology(qa);
        if (b) setBenchmarks(b);
        if (rev) setRevenueRecovery(rev);
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const [topology, setTopology] = useState<any | null>(null);

  return (
    <div className="flex flex-col gap-6 animate-rise-in">
      <div className="flex items-center gap-3">
        <span className="w-1 h-9 bg-accent" />
        <div>
          <div className="flex items-center gap-2 annotation text-accent-strong">
            <span>State Admin</span><span className="text-ink-mut">/</span><span className="text-ink-soft">Analytics</span>
          </div>
          <h1 className="text-3xl font-black text-ink font-display tracking-tight mt-1">Platform Analytics</h1>
          <p className="text-sm text-ink-soft mt-1.5">
            Measured pipeline quality, jurisdiction KPIs and system latencies. Everything here is computed, not claimed.
          </p>
        </div>
      </div>

      {/* Jurisdiction KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-px bg-canvas border-2 border-ink rounded-none overflow-hidden">
        {[
          ['Parcels mapped', summary?.total_mapped_parcels],
          ['3D structures', summary?.total_3d_structures],
          ['Strata units', summary?.total_strata_units],
          ['Verified', summary?.total_verified_properties],
          ['Pending review', summary?.pending_verification_cases],
          ['Completeness', summary?.statewide_data_completeness],
        ].map(([label, value]) => (
          <div key={String(label)} className="bg-chalk p-4">
            <div className="annotation text-ink-mut">{String(label)}</div>
            <div className="mt-1.5 text-2xl font-black font-mono text-ink">{String(value ?? '—')}</div>
          </div>
        ))}
      </div>

      {/* MUNICIPAL REVENUE & TAX EVASION RECOVERY CONSOLE */}
      {revenueRecovery && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-none bg-amber-100 text-amber-800">
                <Coins className="w-5 h-5" />
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-black text-ink font-display tracking-tight">
                    Municipal Revenue & Tax Evasion Recovery Console
                  </h2>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-none bg-rose-100 text-rose-800">
                    MMC Act Sec 260 / 267A
                  </span>
                </div>
                <p className="text-xs text-ink-soft">
                  Zone 8 Airoli Cadastre · Ready Reckoner Rate: ₹{revenueRecovery.ready_reckoner_rate_inr_m2.toLocaleString('en-IN')}/m²
                </p>
              </div>
            </div>
          </div>

          {/* Revenue KPI Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
            <Card className="p-4 bg-chalk to-white border-ink">
              <div className="text-[10px] uppercase font-bold tracking-widest text-rose-800">Total Unassessed Built-Up</div>
              <div className="text-2xl font-black font-mono text-rose-900 mt-1">
                {revenueRecovery.summary.total_unassessed_area_m2.toLocaleString('en-IN')} <span className="text-xs font-normal">m²</span>
              </div>
              <div className="text-[11px] text-rose-700 mt-0.5">{revenueRecovery.summary.total_flagged_properties} violating structures detected</div>
            </Card>

            <Card className="p-4 bg-chalk to-white border-ink">
              <div className="text-[10px] uppercase font-bold tracking-widest text-amber-800">Unpaid Base Property Tax</div>
              <div className="text-2xl font-black font-mono text-amber-900 mt-1">
                ₹{(revenueRecovery.summary.total_evaded_tax_inr / 100000).toFixed(1)} <span className="text-xs font-normal">Lakh</span>
              </div>
              <div className="text-[11px] text-amber-700 mt-0.5">2.5 Years cumulative evasion</div>
            </Card>

            <Card className="p-4 bg-chalk to-white border-ink">
              <div className="text-[10px] uppercase font-bold tracking-widest text-ink">Statutory Penalties (Sec 267A)</div>
              <div className="text-2xl font-black font-mono text-ink mt-1">
                ₹{(revenueRecovery.summary.total_penalties_inr / 100000).toFixed(1)} <span className="text-xs font-normal">Lakh</span>
              </div>
              <div className="text-[11px] text-accent-strong mt-0.5">2x Tax + 18% Compound Interest</div>
            </Card>

            <Card className="p-4 bg-chalk to-white border-ink">
              <div className="text-[10px] uppercase font-bold tracking-widest text-emerald-800">Total Recoverable Sum</div>
              <div className="text-2xl font-black font-mono text-emerald-900 mt-1">
                ₹{revenueRecovery.summary.recovery_potential_crores} <span className="text-xs font-normal">Crore</span>
              </div>
              <div className="text-[11px] text-emerald-700 mt-0.5 font-bold">Direct municipal treasury ROI</div>
            </Card>
          </div>

          {/* Violations Demand Table */}
          <Card className="overflow-hidden border-2 border-ink">
            <div className="px-5 py-3 border-b border-ink bg-canvas flex items-center justify-between">
              <span className="text-xs font-bold text-ink uppercase tracking-widest">
                Unassessed Structures & Action Directives
              </span>
              <span className="text-[11px] font-mono text-ink-soft">
                Click 'Generate Notice' to issue cryptographically sealed statutory order
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-canvas text-ink font-bold border-b border-ink">
                  <tr>
                    <th className="py-2.5 px-4">Building</th>
                    <th className="py-2.5 px-3">ULPIN</th>
                    <th className="py-2.5 px-3 text-right">Unassessed Area</th>
                    <th className="py-2.5 px-3 text-center">Status / Action</th>
                    <th className="py-2.5 px-3 text-right">Assessed Demand</th>
                    <th className="py-2.5 px-4 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                  {revenueRecovery.breakdown.map((row) => (
                    <tr key={row.building_code} className="hover:bg-canvas transition">
                      <td className="py-2.5 px-4 font-sans font-bold text-ink">
                        <div>{row.building_name}</div>
                        <span className="text-[10px] text-accent-strong font-mono">{row.building_code}</span>
                      </td>
                      <td className="py-2.5 px-3 text-ink-soft font-mono">{row.ulpin}</td>
                      <td className="py-2.5 px-3 text-right text-rose-700 font-bold">
                        +{row.unassessed_built_up_m2} m²
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <span
                          className={cn(
                            'px-2 py-0.5 rounded-none text-[10px] font-bold uppercase',
                            row.action === 'DEMOLITION_ORDER_MANDATORY'
                              ? 'bg-rose-100 text-rose-800'
                              : 'bg-amber-100 text-amber-800'
                          )}
                        >
                          {row.action === 'DEMOLITION_ORDER_MANDATORY' ? 'Demolition Order' : 'Compounding Demand'}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right font-bold text-ink">
                        ₹{row.total_demand_inr.toLocaleString('en-IN', { minimumFractionDigits: 0 })}
                      </td>
                      <td className="py-2.5 px-4 text-center">
                        <div className="flex items-center justify-center gap-1.5 font-sans">
                          <button
                            onClick={() => setNoticeBuilding(row.building_code)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-none text-[11px] font-bold text-rose-700 bg-rose-50 border-2 border-ink hover:bg-rose-100 transition"
                          >
                            <FileText className="w-3 h-3" /> Generate Notice
                          </button>
                          <button
                            onClick={() => setBuyerShieldTarget(row.ulpin || row.building_code)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-none text-[11px] font-bold text-emerald-700 bg-emerald-50 border-2 border-ink hover:bg-emerald-100 transition"
                          >
                            <Shield className="w-3 h-3" /> Audit
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* Pipeline quality */}
      <div>
        <div className="flex items-center gap-3 mb-4">
          <span className="w-1 h-5 bg-accent" />
          <span className="annotation text-ink-soft">Algorithmic quality vs synthetic ground truth</span>
        </div>
        {loading && !metrics ? (
          <Skeleton className="h-40 rounded-none" />
        ) : metrics ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="annotation text-accent-strong">Building extraction</span>
                <span className="font-mono text-[10px] text-ink-mut">{metrics.measured_building_extraction.evaluated_points} pts</span>
              </div>
              <div className="text-3xl font-black font-mono text-emerald-700">
                {(metrics.measured_building_extraction.iou * 100).toFixed(1)}% <span className="text-xs font-normal text-ink-soft font-sans">IoU</span>
              </div>
              <div className="text-[11px] text-ink-soft leading-tight">{metrics.measured_building_extraction.method}</div>
              <div className="flex gap-2 text-[11px] font-mono text-ink">
                <span className="bg-canvas px-1.5 py-0.5 rounded-none border-2 border-ink">P {(metrics.measured_building_extraction.precision * 100).toFixed(0)}%</span>
                <span className="bg-canvas px-1.5 py-0.5 rounded-none border-2 border-ink">R {(metrics.measured_building_extraction.recall * 100).toFixed(0)}%</span>
                <span className="bg-canvas px-1.5 py-0.5 rounded-none border-2 border-ink">Δh {metrics.measured_building_extraction.height_error_m} m</span>
              </div>
            </Card>

            <Card className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="annotation text-accent-strong">Floor segmentation</span>
                <span className="font-mono text-[10px] text-ink-mut">{metrics.measured_floor_segmentation.detected_floors}/{metrics.measured_floor_segmentation.ground_truth_floors} floors</span>
              </div>
              <div className="text-3xl font-black font-mono text-emerald-700">
                {(metrics.measured_floor_segmentation.floor_count_accuracy * 100).toFixed(0)}%
              </div>
              <div className="text-[11px] text-ink-soft leading-tight">{metrics.measured_floor_segmentation.method}</div>
              <div className="text-[11px] text-ink-soft">Mean abs error <strong className="font-mono">{metrics.measured_floor_segmentation.mean_absolute_error_floors}</strong> floor</div>
            </Card>

            <Card className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="annotation text-ink">Change detection</span>
                <Badge tone="amber">{metrics.measured_change_detection.detected_change_label}</Badge>
              </div>
              <div className="text-3xl font-black font-mono text-emerald-700">
                {(metrics.measured_change_detection.f1_score * 100).toFixed(0)}% <span className="text-xs font-normal text-ink-soft font-sans">F1</span>
              </div>
              <div className="text-[11px] text-ink-soft leading-tight">{metrics.measured_change_detection.method}</div>
              <div className="flex gap-2 text-[11px] font-mono text-ink">
                <span className="bg-canvas px-1.5 py-0.5 rounded-none border-2 border-ink">P {(metrics.measured_change_detection.precision * 100).toFixed(0)}%</span>
                <span className="bg-canvas px-1.5 py-0.5 rounded-none border-2 border-ink">R {(metrics.measured_change_detection.recall * 100).toFixed(0)}%</span>
              </div>
            </Card>

            <Card className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="annotation text-accent-strong">Topology QA</span>
                <span className="font-mono text-[10px] text-ink-mut">{topology ? `${topology.passed_rules}/${topology.total_rules} rules` : `${metrics.topology_qa_performance.total_rules_evaluated} rules`}</span>
              </div>
              <div className="text-3xl font-black font-mono text-emerald-700">
                {(topology ? (topology.passed_rules / topology.total_rules) * 100 : metrics.topology_qa_performance.overall_qa_pass_rate).toFixed(0)}%
              </div>
              <div className="text-[11px] text-ink-soft leading-tight">R001–R016 against B-17 cadastral relations</div>
              <div className="flex gap-2 text-[11px] text-emerald-700 font-bold">
                <span className="bg-emerald-50 px-1.5 py-0.5 rounded-none">Passed: {topology ? topology.passed_rules : metrics.topology_qa_performance.rules_passed}</span>
                <span className="bg-crimson-50 text-crimson-700 px-1.5 py-0.5 rounded-none">Failed: {topology ? topology.failed_rules : metrics.topology_qa_performance.rules_failed}</span>
              </div>
            </Card>
          </div>
        ) : null}
      </div>

      {/* Latency + benchmark */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card className="p-5">
          <div className="flex items-center gap-2 text-sm font-bold text-ink font-display mb-3">
            <Clock className="w-4 h-4 text-ink-soft" /> System latencies (ms)
          </div>
          {metrics ? (
            <div className="space-y-1.5">
              {Object.entries(metrics.measured_system_latencies_ms ?? {}).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-xs">
                  <span className="text-ink-soft">{k.replace(/_/g, ' ')}</span>
                  <span className="font-mono font-bold text-ink">{String(v)} <span className="text-ink-mut font-normal">ms</span></span>
                </div>
              ))}
            </div>
          ) : (
            <Skeleton className="h-40" />
          )}
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2 text-sm font-bold text-ink font-display mb-3">
            <Zap className="w-4 h-4 text-amber-500" /> Pipeline runtimes &amp; speedup
          </div>
          {benchmarks ? (
            <div className="space-y-2">
              {Object.entries(benchmarks).slice(0, 5).map(([k, v]: [string, any]) => (
                <div key={k} className="flex items-center justify-between text-xs border-b border-ink pb-2 last:border-0">
                  <span className="text-ink-soft capitalize">{k.replace(/_/g, ' ')}</span>
                  <span className="font-mono text-[11px] text-ink">{typeof v === 'number' ? `${v} ms` : String(v)}</span>
                </div>
              ))}
              {benchmarks.total && (
                <div className="flex items-center justify-between text-xs pt-1">
                  <span className="text-ink font-bold">Effective speedup</span>
                  <span className="font-mono font-black text-emerald-700">{benchmarks.speedup_factor || '—'}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs text-ink-soft">
              <Link to="/app/analytics" className="text-accent-strong font-bold hover:underline">Benchmark feed</Link> not available in this session.
              <div className="mt-2 flex items-center gap-2">
                <LineChart className="w-4 h-4 text-ink-mut" />
                Core pipelines (building extraction, floor segmentation, change detection) are executed live against the pilot dataset.
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="flex items-center gap-3">
        <Badge tone="green" dot>honest metrics · computed vs ground truth</Badge>
        <DemoHint />
        <span className="text-[11px] text-ink-mut">No fabricated accuracy figures are displayed.</span>
      </div>

      {/* Action Modals */}
      {noticeBuilding && (
        <DemandNoticeModal
          buildingCode={noticeBuilding}
          isOpen={Boolean(noticeBuilding)}
          onClose={() => setNoticeBuilding(null)}
        />
      )}

      {buyerShieldTarget && (
        <BuyerShieldModal
          initialTarget={buyerShieldTarget}
          isOpen={Boolean(buyerShieldTarget)}
          onClose={() => setBuyerShieldTarget(null)}
        />
      )}
    </div>
  );
};