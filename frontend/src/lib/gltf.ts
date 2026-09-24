import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

export type ModelFormat = 'glb' | 'gltf' | 'obj' | 'stl' | 'unknown';

/** Extracts the file extension (before any query string) from a URL. */
export function modelFormatOf(url: string): ModelFormat {
  const clean = url.split('?')[0].toLowerCase();
  const i = clean.lastIndexOf('.');
  if (i < 0) return 'unknown';
  const ext = clean.slice(i);
  if (ext === '.glb') return 'glb';
  if (ext === '.gltf') return 'gltf';
  if (ext === '.obj') return 'obj';
  if (ext === '.stl') return 'stl';
  return 'unknown';
}

/** Derives a format from a plain file name (used for blob:/object URLs). */
export function formatOfFileName(name: string): ModelFormat {
  const i = name.toLowerCase().lastIndexOf('.');
  if (i < 0) return 'unknown';
  const ext = name.slice(i);
  if (ext === '.glb') return 'glb';
  if (ext === '.gltf') return 'gltf';
  if (ext === '.obj') return 'obj';
  if (ext === '.stl') return 'stl';
  return 'unknown';
}

export const MODEL_FORMAT_LABELS: Record<ModelFormat, string> = {
  glb: 'GLB',
  gltf: 'glTF',
  obj: 'OBJ',
  stl: 'STL',
  unknown: '3D',
};

function onError(reject: (r: Error) => void) {
  return (err: unknown) => reject(err instanceof Error ? err : new Error(String(err)));
}

/**
 * Loads a 3D model and returns a scene group. Dispatches on the URL extension
 * (or an explicit hint for object/blob URLs) — GLB/glTF via GLTFLoader, OBJ via
 * OBJLoader, STL via STLLoader (wrapped into a mesh so every format returns a
 * a mesh so every format returns a THREE.Group-like object).
 */
export function loadModel(url: string, hint?: ModelFormat): Promise<THREE.Group> {
  const fmt = hint ?? modelFormatOf(url);
  if (fmt === 'obj') {
    return new Promise((resolve, reject) => {
      new OBJLoader().load(url, (group) => resolve(group), undefined, onError(reject));
    });
  }
  if (fmt === 'stl') {
    return new Promise((resolve, reject) => {
      new STLLoader().load(
        url,
        (geometry) => {
          const mesh = new THREE.Mesh(
            geometry,
            new THREE.MeshStandardMaterial({ color: 0xdbe4ee, roughness: 0.6, metalness: 0.15, flatShading: true })
          );
          const root = new THREE.Group();
          root.add(mesh);
          resolve(root);
        },
        undefined,
        onError(reject)
      );
    });
  }
  return new Promise((resolve, reject) => {
    new GLTFLoader().load(
      url,
      (gltf) => resolve(gltf.scene ?? gltf.scenes?.[0] ?? new THREE.Group()),
      undefined,
      onError(reject)
    );
  });
}

/** Backwards-compatible alias: loads any supported model from a URL. */
export function loadGlb(url: string): Promise<THREE.Group> {
  return loadModel(url);
}

/** Computes the axis-aligned size of a loaded group via its bounding box. */
export function glbSize(group: THREE.Object3D): { w: number; d: number; h: number } {
  const box = new THREE.Box3().setFromObject(group);
  const size = new THREE.Vector3();
  box.getSize(size);
  return { w: size.x, d: size.y, h: size.z };
}

/**
 * Scales and positions a loaded GLB so it reads as a building proposal:
 * it is placed with its base on the ground plane (z=0), centered on the target
 * footprint, and scaled uniformly so its footprint fits inside the target plot.
 */
export function fitGlbToFootprint(
  group: THREE.Group,
  targetCenter: { x: number; y: number },
  targetW: number,
  targetD: number
): void {
  // glTF is Y-up; our scenes are Z-up. Map local Y -> scene Z so the base of
  // the building stands on the ground plane.
  group.rotation.set(Math.PI / 2, 0, 0);
  const size = glbSize(group);
  const scale = Math.min(targetW / (size.w || 1), targetD / (size.d || 1));
  group.scale.setScalar(scale);
  const box = new THREE.Box3().setFromObject(group);
  const center = box.getCenter(new THREE.Vector3());
  group.position.x += targetCenter.x - center.x;
  group.position.y += targetCenter.y - center.y;
  const base = new THREE.Box3().setFromObject(group).min.z;
  group.position.z += -base;
}

/** Makes every mesh descendant translucent — used for "proposed" previews. */
export function applyTranslucent(group: THREE.Object3D): void {
  group.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if ((mesh as THREE.Mesh).isMesh) {
      const mat = Array.isArray(mesh.material)
        ? mesh.material[0]
        : (mesh.material as THREE.MeshStandardMaterial);
      if (mat) {
        mat.transparent = true;
        mat.opacity = 0.55;
        mat.depthWrite = false;
      }
    }
  });
}

/** Makes every mesh descendant solid and opaque — used for full architectural 3D twin inspection. */
export function applySolid(group: THREE.Object3D): void {
  group.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if ((mesh as THREE.Mesh).isMesh) {
      const mat = Array.isArray(mesh.material)
        ? mesh.material[0]
        : (mesh.material as THREE.MeshStandardMaterial);
      if (mat) {
        mat.transparent = false;
        mat.opacity = 1.0;
        mat.depthWrite = true;
      }
    }
  });
}

/** Disposes all geometries and materials owned by a loaded GLB group. */
export function disposeGlb(group: THREE.Object3D): void {
  group.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if ((mesh as THREE.Mesh).isMesh) {
      mesh.geometry?.dispose();
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      mats.forEach((m) => m?.dispose());
    }
  });
}