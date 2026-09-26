import {
  DecodedPointCloud,
  LidarScene,
  LIDAR_RECORD_STRIDE,
} from './types';

const API_BASE = (import.meta as any).env?.VITE_API_URL || '/api/v1';

export async function fetchLidarScene(): Promise<LidarScene> {
  const res = await fetch(`${API_BASE}/lidar/inspect/scene`);
  if (!res.ok) {
    const detail = await extractError(res);
    throw new Error(detail || `Scene request failed (${res.status})`);
  }
  return res.json();
}

export interface PointQuery {
  step?: number;
  classes?: number[];
  region?: [number, number, number, number];
}

export interface StreamRequest {
  query: PointQuery;
  onProgress?: (loadedBytes: number, totalBytes: number, decodedCount: number) => void;
  signal?: AbortSignal;
}

function extractError(res: Response): Promise<string | null> {
  return res
    .text()
    .then((t) => {
      try {
        const j = JSON.parse(t);
        const detail = j?.detail;
        // `detail` says this deployment is refusing; `data_note` says whether the
        // data is absent in the first place. For LiDAR those are different
        // problems - no open airborne LiDAR exists for India at all - and showing
        // only the first would read as an outage this app could fix.
        const note = j?.data_note;
        if (typeof detail === 'string' && note) return `${detail} ${note}`;
        return detail || note || null;
      } catch {
        return null;
      }
    })
    .catch(() => null);
}

/** Fetches the packed point stream and decodes it into typed arrays. */
export async function fetchLidarPoints(req: StreamRequest): Promise<DecodedPointCloud> {
  const params = new URLSearchParams();
  if (req.query.step && req.query.step > 1) params.set('step', String(req.query.step));
  if (req.query.classes && req.query.classes.length) params.set('classes', req.query.classes.join(','));
  if (req.query.region) params.set('region', req.query.region.join(','));

  const res = await fetch(`${API_BASE}/lidar/inspect/points?${params.toString()}`, {
    signal: req.signal,
  });
  if (!res.ok) {
    const detail = await extractError(res);
    throw new Error(detail || `Point stream failed (${res.status})`);
  }

  const total = Number(res.headers.get('content-length')) || 0;
  const reader = res.body?.getReader();
  if (!reader) {
    const buffer = await res.arrayBuffer();
    return decodeBuffer(new Uint8Array(buffer));
  }

  const chunks: Uint8Array[] = [];
  let received = 0;
  let decodedCount = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.byteLength;
    try {
      decodedCount = decodePointCount(concat(chunks));
    } catch {
      /* header not yet complete */
    }
    req.onProgress?.(received, total || received, decodedCount);
  }

  return decodeBuffer(concat(chunks));
}

function concat(chunks: Uint8Array[]): Uint8Array {
  const size = chunks.reduce((a, c) => a + c.byteLength, 0);
  const out = new Uint8Array(size);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.byteLength;
  }
  return out;
}

function decodePointCount(buf: Uint8Array): number {
  if (buf.byteLength < 12) throw new Error('header incomplete');
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
  if (magic !== 'BHDL') throw new Error('bad magic');
  return dv.getUint32(8, true);
}

function decodeBuffer(buf: Uint8Array): DecodedPointCloud {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
  if (magic !== 'BHDL') throw new Error('Point stream is not a Bhu-Drishti LiDAR payload');
  const stride = dv.getUint32(4, true);
  const count = dv.getUint32(8, true);
  if (stride < LIDAR_RECORD_STRIDE) throw new Error('Unsupported record layout');

  const positions = new Float32Array(count * 3);
  const gps = new Float32Array(count);
  const classification = new Uint8Array(count);
  const intensity = new Uint8Array(count);
  const returnNumber = new Uint8Array(count);

  let off = 12;
  for (let i = 0; i < count; i++) {
    positions[i * 3] = dv.getFloat32(off, true);
    positions[i * 3 + 1] = dv.getFloat32(off + 4, true);
    positions[i * 3 + 2] = dv.getFloat32(off + 8, true);
    gps[i] = dv.getFloat32(off + 12, true);
    classification[i] = dv.getUint8(off + 16);
    intensity[i] = dv.getUint8(off + 17);
    returnNumber[i] = stride >= 19 ? dv.getUint8(off + 18) : 1;
    off += stride;
  }

  return { positions, gps, classification, intensity, returnNumber, count };
}