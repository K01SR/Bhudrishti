/**
 * Frame and scene instrumentation.
 *
 * The map views had no frame timing at all, so the "no frozen frame longer than
 * 100 ms" acceptance gate was unmeasurable. This module is deliberately
 * framework-free: the three.js render loop and the deck.gl overlay both need to
 * report into it from outside React, and the Playwright gate needs to read it
 * from the page. A single mutable store with a subscription callback is the
 * only shape that serves all three.
 *
 * Enabled by the `?perf=1` query parameter. It is inert otherwise, including the
 * rAF loop, so a production build pays one boolean check per frame.
 */

export const LONG_FRAME_MS = 100;

export type LongFrame = {
  /** ms since the previous frame, i.e. the stall the user actually felt. */
  durationMs: number;
  /** performance.now() at the end of the stalled frame. */
  at: number;
  /** What the app was doing when the stall happened, if anything said so. */
  label: string;
};

export type PerfMetrics = {
  fps: number;
  /** Duration of the most recently completed frame. */
  frameMs: number;
  /** Worst frame since the last reset. The headline number for the stall gate. */
  maxFrameMs: number;
  /** Frames over LONG_FRAME_MS since the last reset. */
  longFrames: number;
  /** Total frames counted since the last reset. */
  frames: number;
  /** Features currently held by the active view (3D extruded or 2D drawn). */
  features: number;
  /** three.js renderer.info.render.calls. */
  drawCalls: number;
  triangles: number;
  geometries: number;
  textures: number;
  programs: number;
  /** Time spent assembling the layer list, measured by the caller. */
  layerBuildMs: number;
  /** Time spent building the three.js scene, measured by the caller. */
  sceneBuildMs: number;
  /** Number of scene builds since the last reset. The invalidation tripwire. */
  sceneBuilds: number;
  /** Wall time of the most recent area load, measured by the caller. */
  areaLoadMs: number;
  heapMB: number | null;
  /**
   * Live WebGL contexts: incremented when a canvas acquires one, decremented
   * when it is lost. Chrome stops handing out contexts past ~16 and the symptom
   * is a blank canvas, not an exception.
   */
  webglContexts: number | null;
  /** Free text set by the active view, shown in the overlay. */
  status: string;
};

function emptyMetrics(): PerfMetrics {
  return {
    fps: 0,
    frameMs: 0,
    maxFrameMs: 0,
    longFrames: 0,
    frames: 0,
    features: 0,
    drawCalls: 0,
    triangles: 0,
    geometries: 0,
    textures: 0,
    programs: 0,
    layerBuildMs: 0,
    sceneBuildMs: 0,
    sceneBuilds: 0,
    areaLoadMs: 0,
    heapMB: null,
    webglContexts: null,
    status: '',
  };
}

const state: PerfMetrics = emptyMetrics();
const longFrameLog: LongFrame[] = [];
/** Cap the log so a ten-minute stall spree cannot grow the array without bound. */
const MAX_LOGGED_LONG_FRAMES = 200;

let listeners: Array<() => void> = [];
/** The always-on sampling loop. */
let loopRafId = 0;
/** A one-shot notification frame. Separate from loopRafId: sharing one variable
 *  means the loop's ID makes notify() believe a notify is already pending, so
 *  the overlay never updates again after startup. */
let notifyRafId = 0;
let lastFrameAt = 0;
let fpsWindowStart = 0;
let fpsWindowFrames = 0;

let currentLabel = '';

function heapUsedMb(): number | null {
  // Non-standard and Chromium-only, so it is allowed to be absent.
  const mem = (performance as unknown as { memory?: { usedJSHeapSize?: number } }).memory;
  if (!mem || typeof mem.usedJSHeapSize !== 'number') return null;
  return mem.usedJSHeapSize / (1024 * 1024);
}

function notify() {
  if (notifyRafId) return;
  // rAF rather than microtask: a stall burst often lands many metrics in the
  // same task, and re-rendering the overlay per assignment would itself add
  // main-thread work to the thing being measured.
  notifyRafId = requestAnimationFrame(() => {
    notifyRafId = 0;
    listeners.forEach((fn) => fn());
  });
}

function frame(now: number) {
  if (lastFrameAt) {
    const delta = now - lastFrameAt;
    state.frameMs = delta;
    state.frames += 1;
    if (delta > state.maxFrameMs) state.maxFrameMs = delta;
    if (delta > LONG_FRAME_MS) {
      state.longFrames += 1;
      if (longFrameLog.length < MAX_LOGGED_LONG_FRAMES) {
        longFrameLog.push({ durationMs: delta, at: now, label: currentLabel });
      }
    }

    fpsWindowFrames += 1;
    if (now - fpsWindowStart >= 500) {
      state.fps = (fpsWindowFrames * 1000) / (now - fpsWindowStart);
      fpsWindowStart = now;
      fpsWindowFrames = 0;
    }
  }
  lastFrameAt = now;

  const heap = heapUsedMb();
  if (heap !== null) state.heapMB = heap;

  notify();
  loopRafId = requestAnimationFrame(frame);
}

/** Reads `?perf=1` (also accepts a bare `?perf`). */
export function isPerfEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  const raw = new URLSearchParams(window.location.search).get('perf');
  return raw !== null && raw !== '0' && raw !== 'false';
}

export function startPerf(): void {
  if (loopRafId) return;
  lastFrameAt = 0;
  fpsWindowStart = performance.now();
  fpsWindowFrames = 0;
  loopRafId = requestAnimationFrame(frame);
}

export function stopPerf(): void {
  if (loopRafId) cancelAnimationFrame(loopRafId);
  loopRafId = 0;
  if (notifyRafId) cancelAnimationFrame(notifyRafId);
  notifyRafId = 0;
}

export function subscribePerf(fn: () => void): () => void {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((l) => l !== fn);
  };
}

/** Read-only view for the overlay, so callers cannot mutate the store. */
export function getPerf(): Readonly<PerfMetrics> {
  return state;
}

/** Patch one or more fields. Undefined values are ignored, not zeroed. */
export function setPerf(patch: Partial<PerfMetrics>): void {
  let changed = false;
  (Object.keys(patch) as Array<keyof PerfMetrics>).forEach((key) => {
    const next = patch[key];
    if (next === undefined || state[key] === next) return;
    // Assign through a widened view: PerfMetrics is readonly for consumers but
    // the store itself is the only writer.
    (state as Record<string, unknown>)[key] = next;
    changed = true;
  });
  if (changed) notify();
}

/** Tag the next long frame, so a stall can be attributed to a known action. */
export function labelPerf(label: string): void {
  currentLabel = label;
}

/** Times a synchronous block and reports it. Returns the elapsed ms. */
export function measurePerf(key: 'layerBuildMs' | 'sceneBuildMs', fn: () => void): void {
  const t0 = performance.now();
  try {
    fn();
  } finally {
    const patch: Partial<PerfMetrics> = { [key]: performance.now() - t0 } as Partial<PerfMetrics>;
    if (key === 'sceneBuildMs') patch.sceneBuilds = state.sceneBuilds + 1;
    setPerf(patch);
  }
}

export function recordAreaLoad(ms: number): void {
  setPerf({ areaLoadMs: ms });
}

/**
 * Clears rate counters but keeps the rAF loop, the enabled state and the
 * cumulative counters.
 *
 * sceneBuilds and webglContexts survive a reset on purpose. Both are cumulative
 * facts about the page, not rates: "the scene has been built 3 times since load"
 * stays true across a window boundary, and zeroing them would let a test that
 * resets between measurement windows compare two unrelated numbers.
 */
export function resetPerf(): void {
  const heap = state.heapMB;
  const ctx = state.webglContexts;
  const builds = state.sceneBuilds;
  const label = currentLabel;
  Object.assign(state, emptyMetrics());
  state.heapMB = heap;
  state.webglContexts = ctx;
  state.sceneBuilds = builds;
  currentLabel = label;
  longFrameLog.length = 0;
  lastFrameAt = 0;
  notify();
}

export function getLongFrames(): readonly LongFrame[] {
  return longFrameLog;
}

/**
 * Test surface. The Playwright gate asserts on this rather than scraping the
 * overlay's text, so the gate keeps working if the overlay layout changes.
 */
export type PerfProbe = {
  enabled: boolean;
  metrics: PerfMetrics;
  longFrames: LongFrame[];
  reset: () => void;
  label: (s: string) => void;
};

declare global {
  interface Window {
    __PERF__?: PerfProbe;
  }
}

/**
 * Count live WebGL contexts.
 *
 * The 3D view builds a fresh WebGLRenderer on every scene rebuild and its
 * cleanup used to call renderer.dispose() without forceContextLoss(), so
 * contexts accumulated. Chrome starts failing new contexts at roughly 16 and
 * the symptom is a silently blank canvas rather than an exception, so the count
 * is the only way to observe it building up.
 *
 * Increments on getContext and decrements on the canvas' webglcontextlost event,
 * which is what forceContextLoss() fires. A getContext call that returns an
 * existing context does not increment, because the patch only counts a context
 * the first time a canvas asks for one. That makes the number live contexts
 * rather than requests.
 *
 * The prototype is patched only under `?perf=1`.
 */
export function trackWebglContexts(): void {
  const proto = HTMLCanvasElement.prototype as unknown as {
    getContext: (type: string, ...rest: unknown[]) => unknown;
  };
  const original = proto.getContext;
  const counted = new WeakSet<HTMLCanvasElement>();

  proto.getContext = function patchedGetContext(this: HTMLCanvasElement, type: string, ...rest: unknown[]) {
    if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
      const ctx = original.call(this, type, ...rest);
      if (ctx && !counted.has(this)) {
        counted.add(this);
        state.webglContexts = (state.webglContexts ?? 0) + 1;
        this.addEventListener(
          'webglcontextlost',
          () => {
            state.webglContexts = Math.max(0, (state.webglContexts ?? 0) - 1);
            notify();
          },
          { once: true },
        );
        notify();
      }
      return ctx;
    }
    return original.call(this, type, ...rest);
  };
}

export function installPerfProbe(): void {
  window.__PERF__ = {
    enabled: isPerfEnabled(),
    metrics: state,
    longFrames: longFrameLog,
    reset: resetPerf,
    label: labelPerf,
  };
}
