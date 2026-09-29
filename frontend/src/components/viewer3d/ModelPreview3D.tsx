import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { loadModel, modelFormatOf, MODEL_FORMAT_LABELS, ModelFormat } from '../../lib/gltf';
import { Box, RefreshCw } from 'lucide-react';

interface Props {
  url: string | null;
  height?: number;
  className?: string;
  name?: string;
  spinning?: boolean;
  /** Explicit format used when the URL is a blob:/object URL with no extension. */
  format?: ModelFormat;
}

/**
 * Lightweight standalone 3D preview for any model URL (GLB/glTF/OBJ/STL).
 * Centers and fits the loaded geometry in view with a soft grid and auto-rotate;
 * used to show a builder their uploaded model instantly.
 */
export const ModelPreview3D: React.FC<Props> = ({ url, height = 220, className = '', name, spinning = true, format }) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [sizing, setSizing] = useState<{ w: number; d: number } | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !url) return;
    let disposed = false;
    setFailed(null);
    setSizing(null);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const scene = new THREE.Scene();
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 1.1);
    key.position.set(30, 60, 40);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x9db4ff, 0.4);
    fill.position.set(-40, 20, -30);
    scene.add(fill);
    scene.add(new THREE.GridHelper(60, 60, 0x8ba5c4, 0x2c3a52));

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000);
    camera.position.set(34, 38, 56);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate = spinning;
    controls.autoRotateSpeed = 2.2;
    controls.target.set(0, 0, 0);

    const group = new THREE.Group();
    group.name = 'PREVIEW_MODEL';
    scene.add(group);

    const setSize = () => {
      const w = host.clientWidth || 320;
      const h = height;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    setSize();
    host.appendChild(renderer.domElement);
    const ro = new ResizeObserver(setSize);
    ro.observe(host);

    let animId = 0;
    const loop = () => {
      animId = requestAnimationFrame(loop);
      controls.update();
      renderer.render(scene, camera);
    };
    loop();

    loadModel(url, format)
      .then((g) => {
        if (disposed) return;
        g.traverse((child) => {
          const mesh = child as THREE.Mesh;
          if (mesh.isMesh) mesh.castShadow = true;
        });
        const box = new THREE.Box3().setFromObject(g);
        const size = new THREE.Vector3();
        box.getSize(size);
        setSizing({ w: size.x, d: size.z });
        const maxEdge = Math.max(size.x, Math.max(size.y, size.z)) || 1;
        const scale = 24 / maxEdge;
        g.scale.multiplyScalar(scale);
        group.add(g);
        const b2 = new THREE.Box3().setFromObject(g);
        const c = b2.getCenter(new THREE.Vector3());
        group.position.x -= c.x;
        group.position.z -= c.z;
        group.position.y -= b2.min.y;
      })
      .catch((err) => {
        if (!disposed) setFailed(String(err?.message || err));
      });

    const updateRotation = () => { controls.autoRotate = spinning; };
    updateRotation();

    return () => {
      disposed = true;
      ro.disconnect();
      cancelAnimationFrame(animId);
      group.removeFromParent();
      group.traverse((child) => {
        const mesh = child as THREE.Mesh;
        if (mesh.isMesh) {
          mesh.geometry?.dispose();
          const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          mats.forEach((m) => m?.dispose());
        }
      });
      controls.dispose();
      renderer.dispose();
      host.removeChild(renderer.domElement);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, height, spinning, format]);

  if (!url) return null;
  const fmt = format ?? modelFormatOf(url);
  return (
    <div className={className}>
      <div ref={hostRef} style={{ height }} className="relative w-full overflow-hidden rounded-xl bg-gradient-to-br from-slate-900 to-slate-800" />
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-ink-mut">
        <span className="inline-flex items-center gap-1 font-mono font-bold text-ink bg-ink/5 px-1.5 py-0.5 rounded">{MODEL_FORMAT_LABELS[fmt]}</span>
        {name && <span className="font-mono truncate">{name}</span>}
        {sizing && <span className="font-mono">footprint {Math.round(sizing.w)} × {Math.round(sizing.d)} units</span>}
        {spinning && (
          <span className="inline-flex items-center gap-1">
            <RefreshCw className="w-3 h-3" /> auto-orbit
          </span>
        )}
        {failed && (
          <span className="inline-flex items-center gap-1 text-red-600 font-bold">
            <Box className="w-3 h-3" /> {failed.slice(0, 60)}
          </span>
        )}
      </div>
    </div>
  );
};