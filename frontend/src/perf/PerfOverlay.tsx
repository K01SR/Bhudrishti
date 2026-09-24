import { useEffect, useState } from 'react';
import { LONG_FRAME_MS, getPerf, isPerfEnabled, resetPerf, subscribePerf, type PerfMetrics } from './perf';

/**
 * Frame budget HUD. Rendered only under `?perf=1`.
 *
 * Deliberately avoids box-shadow, backdrop-filter and any per-frame animation.
 * An overlay that repaints expensive effects would show up in the very numbers
 * it reports, which is the failure mode the Phase 0 instrumentation exists to
 * rule out.
 */
function Row({ label, value, bad }: { label: string; value: string; bad?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-6 whitespace-nowrap">
      <span className="text-ink-mut uppercase tracking-widest">{label}</span>
      <span className={`font-mono ${bad ? 'text-crimson-600' : 'text-ink'}`}>{value}</span>
    </div>
  );
}

function num(n: number, digits = 0): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export default function PerfOverlay() {
  const [on] = useState(() => isPerfEnabled());
  const [m, setM] = useState<Readonly<PerfMetrics>>(() => getPerf());

  useEffect(() => {
    if (!on) return;
    setM(getPerf());
    return subscribePerf(() => setM(getPerf()));
  }, [on]);

  if (!on) return null;

  const stalled = m.maxFrameMs > LONG_FRAME_MS;

  return (
    <div
      data-testid="perf-overlay"
      aria-hidden="true"
      className="pointer-events-none fixed bottom-3 left-3 z-[9999] select-none border-2 border-ink bg-chalk px-3 py-2 font-mono text-[10px] leading-tight"
    >
      <div className="mb-1 flex items-center justify-between gap-6 border-b-2 border-ink pb-1">
        <span className="font-black uppercase tracking-widest">PERF</span>
        <button
          type="button"
          className="pointer-events-auto border-2 border-ink bg-chalk px-1 font-black uppercase"
          onClick={resetPerf}
        >
          reset
        </button>
      </div>

      <div className="grid gap-y-0.5">
        <Row label="fps" value={num(m.fps, 1)} bad={m.fps > 0 && m.fps < 30} />
        <Row label="frame" value={`${num(m.frameMs, 1)} ms`} bad={m.frameMs > LONG_FRAME_MS} />
        <Row
          label={`max (${num(m.frames)} f)`}
          value={`${num(m.maxFrameMs, 1)} ms`}
          bad={stalled}
        />
        <Row label={`< ${LONG_FRAME_MS} ms stalls`} value={num(m.longFrames)} bad={m.longFrames > 0} />

        <div className="my-1 border-t border-ink/20" />

        <Row label="features" value={num(m.features)} />
        <Row label="draw calls" value={num(m.drawCalls)} bad={m.drawCalls > 400} />
        <Row label="triangles" value={num(m.triangles)} />
        <Row label="geometries" value={num(m.geometries)} bad={m.geometries > 1000} />
        <Row label="textures" value={num(m.textures)} />
        <Row label="programs" value={num(m.programs)} />

        <div className="my-1 border-t border-ink/20" />

        <Row label="scene builds" value={num(m.sceneBuilds)} bad={m.sceneBuilds > 1} />
        <Row label="layer build" value={`${num(m.layerBuildMs, 1)} ms`} bad={m.layerBuildMs > 100} />
        <Row label="scene build" value={`${num(m.sceneBuildMs, 1)} ms`} bad={m.sceneBuildMs > 100} />
        <Row label="area load" value={`${num(m.areaLoadMs, 0)} ms`} />
        <Row label="heap" value={m.heapMB === null ? 'n/a' : `${num(m.heapMB, 1)} MB`} />
        <Row label="webgl ctx" value={m.webglContexts === null ? 'n/a' : num(m.webglContexts)} bad={(m.webglContexts ?? 0) > 12} />
      </div>

      {m.status ? (
        <div className="mt-1 max-w-[20rem] truncate border-t border-ink/20 pt-1 text-ink-soft">{m.status}</div>
      ) : null}
    </div>
  );
}
