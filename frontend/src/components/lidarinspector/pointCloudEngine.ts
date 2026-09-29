import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import {
  CameraPreset,
  CLASS_COLORS,
  ColorMode,
  DecodedPointCloud,
  LidarLevel,
  LidarScene,
  LidarSelection,
  PointShape,
} from './types';

export interface EngineCallbacks {
  onSelectProperty?: (ulpin: string, at: { x: number; y: number; z: number } | null) => void;
  onInspectPoint?: (info: InspectInfo | null) => void;
  onStatus?: (s: EngineStatus) => void;
  onMeasure?: (reads: MeasureRead[]) => void;
}

export interface InspectInfo {
  x: number;
  y: number;
  z: number;
  classification: number;
  intensity: number;
  gps: number;
  color: string;
  inHeroParcel: boolean;
  ulpin: string | null;
}

export interface MeasureRead {
  distance: number;
  height: number | null;
}

export interface EngineStatus {
  fps: number;
  rendered: number;
  memoryMB: number;
}

export interface ColorModeOptions {
  selection?: LidarSelection | null;
  focusParcel?: boolean;
  isolateBuilding?: boolean;
  floorLevel?: LidarLevel | null;
  vSlice?: { x: number; width: number } | null;
}

export interface SliceBand {
  min: number;
  max: number;
  mode: 'dim' | 'hide';
}

export interface ClipBox {
  min: number[];
  max: number[];
}

export interface LayerVisibility {
  lidar: boolean;
  parcels: boolean;
  footprint: boolean;
  model: boolean;
  grid: boolean;
}

const FOG_COLOR = new THREE.Color(0x05070d);

function pointInRing(x: number, y: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    const intersect =
      (yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi || 1e-9) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

const VERT = /* glsl */ `
  attribute float aId;
  varying vec3 vColor;
  varying float vFogDepth;
  uniform float uSize;
  uniform float uPixelRatio;
  uniform float uMinPx;
  uniform float uMaxPx;
  uniform float uRefDist;
  void main() {
    vColor = color;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    float dist = max(1.0, -mvPosition.z);
    float wanted = uSize * (uRefDist / dist);
    gl_PointSize = clamp(wanted, uMinPx, uMaxPx) * uPixelRatio;
    vFogDepth = dist;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const FRAG = /* glsl */ `
  varying vec3 vColor;
  varying float vFogDepth;
  uniform float uOpacity;
  uniform vec3 uTint;
  uniform float uFogDensity;
  uniform vec3 uFogColor;
  uniform bool uHardClip;
  uniform float uClipMinZ;
  uniform float uClipMaxZ;
  uniform float uGlow;
  uniform int uPointShape; // 0: 3D Spherical Splat (EDL), 1: Antialiased Disc, 2: Square Voxel
  uniform float uEdlStrength;

  void main() {
    vec2 coord = gl_PointCoord * 2.0 - 1.0;
    float r2 = dot(coord, coord);

    if (uPointShape == 0) {
      // Photorealistic 3D Spherical Splat with Eye Dome Lighting (EDL) & Normal Shading
      if (r2 > 1.0) discard;
      float nz = sqrt(max(0.0, 1.0 - r2));
      vec3 normal = normalize(vec3(coord.x, -coord.y, nz));
      
      // Dynamic sunlight direction (upper-front right)
      vec3 lightDir = normalize(vec3(0.35, 0.45, 0.82));
      float diff = max(0.32, dot(normal, lightDir));
      
      // Specular highlight for metallic / glass / structural returns
      vec3 halfDir = normalize(lightDir + vec3(0.0, 0.0, 1.0));
      float spec = pow(max(0.0, dot(normal, halfDir)), 24.0) * 0.35;
      
      // Eye Dome Lighting (EDL) rim darkening for crisp boundary definition
      float rim = pow(nz, 0.35 + 0.45 * uEdlStrength);
      
      vec3 litColor = vColor * diff * rim + vec3(spec);
      float core = pow(nz, 2.0);
      litColor = mix(litColor, clamp(vColor * 1.5, vec3(0.0), vec3(1.0)), core * uGlow);
      
      float fog = 1.0 - exp(-uFogDensity * uFogDensity * vFogDepth * vFogDepth);
      litColor = mix(litColor, uFogColor, clamp(fog, 0.0, 0.92));
      gl_FragColor = vec4(litColor * uTint, uOpacity);
    } else if (uPointShape == 1) {
      // Smooth Antialiased Disc
      if (r2 > 1.0) discard;
      float mask = 1.0 - smoothstep(0.65, 1.0, r2);
      float core = 1.0 - smoothstep(0.0, 0.7, sqrt(r2));
      vec3 col = vColor * (1.0 - uGlow) + clamp(vColor * 1.35, vec3(0.0), vec3(1.0)) * core * uGlow;
      float fog = 1.0 - exp(-uFogDensity * uFogDensity * vFogDepth * vFogDepth);
      col = mix(col, uFogColor, clamp(fog, 0.0, 0.92));
      gl_FragColor = vec4(col * uTint, mask * uOpacity);
    } else {
      // Sharp Square Voxel (GIS Cell)
      float fog = 1.0 - exp(-uFogDensity * uFogDensity * vFogDepth * vFogDepth);
      vec3 col = mix(vColor, uFogColor, clamp(fog, 0.0, 0.92));
      gl_FragColor = vec4(col * uTint, uOpacity);
    }
  }
`;

class PointCloudEngine {
  private container: HTMLElement;
  private labelLayer: HTMLElement;
  private scene: LidarScene;
  private cb: EngineCallbacks;

  private renderer!: THREE.WebGLRenderer;
  private camera!: THREE.PerspectiveCamera;
  private controls!: OrbitControls;
  private scene3d = new THREE.Scene();
  private pointsMesh: THREE.Points | null = null;
  private pointsGeo: THREE.BufferGeometry | null = null;
  private pointsMat: THREE.ShaderMaterial | null = null;

  private cloud: DecodedPointCloud | null = null;
  private colorArray: Float32Array = new Float32Array(0);
  private raf = 0;
  private disposed = false;
  private resizeObs?: ResizeObserver;

  private groups = {
    points: new THREE.Group(),
    boundaries: new THREE.Group(),
    footprint: new THREE.Group(),
    model: new THREE.Group(),
    grid: new THREE.Group(),
    measure: new THREE.Group(),
  };

  private ringLines: THREE.LineLoop[] = [];
  private heroRingLines: THREE.LineLoop[] = [];
  private footprintLines: THREE.LineLoop[] = [];
  private floorMarks: THREE.LineSegments[] = [];
  private modelMeshes: THREE.Mesh[] = [];
  private gridHelper: THREE.GridHelper | null = null;

  private labels: { el: HTMLDivElement; pos: THREE.Vector3 }[] = [];

  private mode: ColorMode = 'monochrome';
  private modeOpts: ColorModeOptions = {};
  private visibleClasses: Set<number> | null = null;
  private sliceBand: SliceBand | null = null;
  private clipBox: ClipBox | null = null;
  private layers: LayerVisibility = {
    lidar: true,
    parcels: true,
    footprint: true,
    model: false,
    grid: true,
  };

  private raycaster = new THREE.Raycaster();
  private pointerNDC = new THREE.Vector2();
  private activeTool: 'select' | 'measure' = 'select';
  private measurePts: THREE.Vector3[] = [];
  private measureMarkers: THREE.Object3D[] = [];
  private measureLines: THREE.Object3D[] = [];
  private measureLabels: HTMLDivElement[] = [];
  private lastClickTime = 0;

  private camAnim: {
    t0: number;
    dur: number;
    fromPos: THREE.Vector3;
    toPos: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toTarget: THREE.Vector3;
  } | null = null;

  private frameCount = 0;
  private lastFpsEmit = performance.now();
  private hoverRaycastTimer = 0;

  private heroMark: Uint8Array = new Uint8Array(0);
  private fpMark: Uint8Array = new Uint8Array(0);

  constructor(container: HTMLElement, labelLayer: HTMLElement, scene: LidarScene, cb: EngineCallbacks = {}) {
    this.container = container;
    this.labelLayer = labelLayer;
    this.scene = scene;
    this.cb = cb;
    this.initRenderer();
  }

  private initRenderer() {
    const w = this.container.clientWidth || 1;
    const h = this.container.clientHeight || 1;

    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(w, h);
    this.renderer.setClearColor(FOG_COLOR, 1);
    this.renderer.domElement.style.display = 'block';
    this.container.appendChild(this.renderer.domElement);

    const c = this.scene.stats.center;
    this.camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 3000);
    this.camera.up.set(0, 0, 1);
    const d = this.scene.stats.span_m[0] + this.scene.stats.span_m[1];
    this.camera.position.set(c[0] + d * 0.7, c[1] - d * 0.7, c[2] + d * 0.55);
    this.camera.near = 0.2;

    const scene = this.scene3d;
    scene.background = FOG_COLOR.clone();
    scene.fog = new THREE.FogExp2(FOG_COLOR, 0.0018);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(c[0], c[1], c[2]);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 6;
    this.controls.maxDistance = 900;
    this.controls.autoRotate = false;
    this.controls.update();

    for (const g of Object.values(this.groups)) scene.add(g);
    this.buildGrid();
    this.buildBoundaries();
    this.buildFootprint();
    this.buildModel();

    const onResize = () => {
      const cw = this.container.clientWidth || 1;
      const ch = this.container.clientHeight || 1;
      this.camera.aspect = cw / ch;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(cw, ch);
    };
    this.resizeObs = new ResizeObserver(onResize);
    this.resizeObs.observe(this.container);

    const canvas = this.renderer.domElement;
    canvas.addEventListener('pointerdown', this.onPointerDown);
    canvas.addEventListener('pointerup', this.onPointerUp);
    canvas.addEventListener('pointermove', this.onPointerMove);
    canvas.addEventListener('dblclick', this.onDblClick);

    this.raf = requestAnimationFrame(this.tick);
  }

  /* ------------------------------------------------------------------ */
  /* Data                                                                */
  /* ------------------------------------------------------------------ */

  loadPointCloud(cloud: DecodedPointCloud) {
    this.cloud = cloud;
    const n = cloud.count;
    this.heroMark = new Uint8Array(n);
    this.fpMark = new Uint8Array(n);
    this.updateSelectionMarks(this.modeOpts?.selection);

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(cloud.positions.slice(), 3));
    geo.setAttribute('aId', new THREE.BufferAttribute(this.makeIds(n), 1));
    geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    geo.setIndex(new THREE.Uint32BufferAttribute(this.makeIds(n), 1));
    this.pointsGeo = geo;

    this.colorArray = new Float32Array(n * 3);
    this.computeColors();

    this.pointsMat = new THREE.ShaderMaterial({
      uniforms: {
        uSize: { value: 2.2 },
        uPixelRatio: { value: this.renderer.getPixelRatio() },
        uMinPx: { value: 1 },
        uMaxPx: { value: 16 },
        uRefDist: { value: 90 },
        uOpacity: { value: 0.95 },
        uTint: { value: new THREE.Vector3(1, 1, 1) },
        uFogDensity: { value: 0.0018 },
        uFogColor: { value: FOG_COLOR.clone() },
        uHardClip: { value: false },
        uClipMinZ: { value: -100 },
        uClipMaxZ: { value: 100 },
        uGlow: { value: 0.35 },
        uPointShape: { value: 0 }, // 0: 3D Splat (EDL), 1: Disc, 2: Voxel
        uEdlStrength: { value: 0.75 },
      },
      vertexColors: true,
      transparent: true,
      depthWrite: true,
      depthTest: true,
      blending: THREE.NormalBlending,
      vertexShader: VERT,
      fragmentShader: FRAG,
    });

    const pts = new THREE.Points(geo, this.pointsMat);
    pts.frustumCulled = true;
    this.pointsMesh = pts;
    this.groups.points.add(pts);

    this.applyVisibility();
    this.rebuildIndex();
    this.emitStatus();
  }

  private updateSelectionMarks(selection?: LidarSelection | null) {
    if (!this.cloud) return;
    const n = this.cloud.count;
    const pos = this.cloud.positions;
    const ring = selection?.parcelRing?.length
      ? selection.parcelRing
      : this.scene.ground_truth.parcel_ring;
    const fp = selection?.footprint?.length
      ? selection.footprint
      : this.scene.ground_truth.footprint;

    for (let i = 0; i < n; i++) {
      const x = pos[i * 3];
      const y = pos[i * 3 + 1];
      this.heroMark[i] = ring && ring.length && pointInRing(x, y, ring) ? 1 : 0;
      this.fpMark[i] = fp && fp.length && pointInRing(x, y, fp) ? 1 : 0;
    }
  }

  private makeIds(n: number): Float32Array {
    const a = new Float32Array(n);
    for (let i = 0; i < n; i++) a[i] = i;
    return a;
  }

  /* ------------------------------------------------------------------ */
  /* Coloring / emphasis                                                  */
  /* ------------------------------------------------------------------ */

  setColorMode(mode: ColorMode) {
    this.mode = mode;
    this.computeColors();
  }

  setColorModeOptions(opts: ColorModeOptions) {
    this.modeOpts = opts;
    if (this.cloud) {
      this.updateSelectionMarks(opts.selection);
    }
    this.computeColors();
    this.rebuildIndex();
  }

  setPointSize(px: number) {
    if (this.pointsMat) {
      this.pointsMat.uniforms.uSize.value = Math.max(0.4, px);
    }
  }

  setPointShape(shape: PointShape) {
    if (this.pointsMat) {
      const code = shape === 'splat' ? 0 : shape === 'disc' ? 1 : 2;
      this.pointsMat.uniforms.uPointShape.value = code;
    }
  }

  setEdlStrength(strength: number) {
    if (this.pointsMat) {
      this.pointsMat.uniforms.uEdlStrength.value = Math.max(0, Math.min(1, strength));
    }
  }

  getCameraDistance(): number {
    return this.camera.position.distanceTo(this.controls.target);
  }

  setGlow(glow: number) {
    if (this.pointsMat) {
      this.pointsMat.uniforms.uGlow.value = Math.max(0, Math.min(1, glow));
    }
  }

  setSliceBand(band: SliceBand | null) {
    this.sliceBand = band;
    this.applyHardClip();
    this.computeColors();
  }

  setClipBox(box: ClipBox | null) {
    this.clipBox = box;
    this.applyHardClip();
  }

  setVisibleClasses(codes: Set<number> | null) {
    this.visibleClasses = codes;
    this.rebuildIndex();
  }

  setQuality(step: number) {
    this.qualityStep = step;
    this.rebuildIndex();
  }

  private qualityStep = 1;

  private applyHardClip() {
    const mat = this.pointsMat;
    if (!mat) return;
    const slice = this.sliceBand && this.sliceBand.mode === 'hide' ? this.sliceBand : null;
    mat.uniforms.uHardClip.value = !!slice || !!this.clipBox;
    mat.uniforms.uClipMinZ.value = slice ? slice.min : -1000;
    mat.uniforms.uClipMaxZ.value = slice ? slice.max : 1000;
  }

  private emphasis(z: number, hero: number, fp: number, x: number): number {
    const o = this.modeOpts;
    let v = 1;

    if (o.selection && o.isolateBuilding) {
      v = (fp === 1 || hero === 1) ? 1.25 : 0.03;
    } else if (o.selection && o.focusParcel) {
      v = (fp === 1 || hero === 1) ? 1.15 : 0.22;
    }
    if (this.sliceBand && this.sliceBand.mode === 'dim') {
      const inBand = z >= this.sliceBand.min && z <= this.sliceBand.max;
      v = Math.min(v, inBand ? 1.6 : 0.25);
    }
    if (o.floorLevel) {
      const inBand = z >= o.floorLevel.min_z && z <= o.floorLevel.max_z;
      v = Math.min(v, inBand ? 1.5 : 0.25);
    }
    if (o.vSlice) {
      const hw = Math.max(0.05, o.vSlice.width / 2);
      const inBand = Math.abs(x - o.vSlice.x) <= hw;
      v = Math.min(v, inBand ? 1.7 : 0.25);
    }
    return v;
  }

  private computeColors() {
    const cloud = this.cloud;
    if (!cloud || !this.pointsGeo) return;
    const n = cloud.count;
    const pos = cloud.positions;
    const cls = cloud.classification;
    const inten = cloud.intensity;
    const c = new THREE.Color();
    const zMin = this.scene.stats.bounds.min[2];
    const zMax = this.scene.stats.bounds.max[2];
    const spanZ = (zMax - zMin) || 1;

    for (let i = 0; i < n; i++) {
      const z = pos[i * 3 + 2];
      const x = pos[i * 3];
      const t = Math.max(0, Math.min(1, (z - zMin) / spanZ));
      let r = 0.75;
      let g = 0.8;
      let b = 0.9;

      switch (this.mode) {
        case 'monochrome': {
          r = g = b = 0.62 + 0.3 * t;
          break;
        }
        case 'elevation': {
          // High-contrast 8-stop Turbo Spectrum elevation ramp
          if (t < 0.12) {
            const p = t / 0.12;
            r = 0.12 + 0.08 * p; g = 0.18 + 0.35 * p; b = 0.65 + 0.35 * p;
          } else if (t < 0.3) {
            const p = (t - 0.12) / 0.18;
            r = 0.2 - 0.12 * p; g = 0.53 + 0.42 * p; b = 1.0 - 0.15 * p;
          } else if (t < 0.5) {
            const p = (t - 0.3) / 0.2;
            r = 0.08 + 0.65 * p; g = 0.95 + 0.05 * p; b = 0.85 - 0.65 * p;
          } else if (t < 0.72) {
            const p = (t - 0.5) / 0.22;
            r = 0.73 + 0.27 * p; g = 1.0 - 0.45 * p; b = 0.2 - 0.15 * p;
          } else {
            const p = (t - 0.72) / 0.28;
            r = 1.0; g = 0.55 - 0.42 * p; b = 0.05 + 0.6 * p;
          }
          break;
        }
        case 'gradient': {
          c.setHSL(t * 0.78, 0.9, 0.45);
          r = c.r; g = c.g; b = c.b;
          break;
        }
        case 'intensity': {
          // Golden laser scanner radar return
          const v = inten[i] / 255;
          c.setHSL(0.11, 0.95, 0.14 + v * 0.82);
          r = c.r; g = c.g; b = c.b;
          break;
        }
        case 'classification': {
          c.set(CLASS_COLORS[cls[i]] || '#7a8290');
          r = c.r; g = c.g; b = c.b;
          break;
        }
        case 'epoch2_delta': {
          // No independent second pass exists for this capture, so there is no
          // delta to draw. Previously this highlighted `rn === 2 ||
          // intensity >= 240`, which flagged 237 ordinary points in the shipped
          // cloud purely because their normalised intensity landed near the top
          // of the range, and labelled them unauthorized construction. A delta
          // cannot be derived from one pass, so the honest rendering is a flat
          // "unavailable" wash instead of an alert.
          r = 0.42; g = 0.44; b = 0.47;
          break;
        }
        case 'rgb':
        default: {
          // Realistic architectural rendering. No point is tinted as an alert
          // here: with a single pass there is no observed change to show.
          if (cls[i] === 2) {
            // Ground terrain
            const v = inten[i] / 255;
            r = 0.22 + 0.1 * v;
            g = 0.2 + 0.08 * v;
            b = 0.18 + 0.06 * v;
          } else if (cls[i] === 5) {
            // High vegetation
            const v = inten[i] / 255;
            r = 0.12 + 0.06 * v;
            g = 0.55 + 0.28 * v;
            b = 0.22 + 0.12 * v;
          } else if (cls[i] === 6) {
            // Building
            if (t > 0.82) {
              // Rooftop terracotta
              r = 0.85; g = 0.4; b = 0.18;
            } else {
              // Facade concrete / structural slabs
              const v = inten[i] / 255;
              r = 0.72 + 0.18 * v;
              g = 0.76 + 0.16 * v;
              b = 0.82 + 0.14 * v;
            }
          } else {
            r = g = b = 0.65 + 0.2 * t;
          }
          break;
        }
      }

      const dim = this.emphasis(z, this.heroMark[i], this.fpMark[i], x);
      this.colorArray[i * 3] = r * dim;
      this.colorArray[i * 3 + 1] = g * dim;
      this.colorArray[i * 3 + 2] = b * dim;
    }

    (this.pointsGeo.getAttribute('color') as THREE.BufferAttribute).array = this.colorArray;
    (this.pointsGeo.getAttribute('color') as THREE.BufferAttribute).needsUpdate = true;
  }

  private rebuildIndex() {
    if (!this.cloud || !this.pointsMesh || !this.pointsGeo) return;
    const n = this.cloud.count;
    const keep: number[] = [];
    const step = Math.max(1, this.qualityStep);
    const isolate = !!(this.modeOpts?.isolateBuilding && this.modeOpts?.selection);

    for (let i = 0; i < n; i++) {
      if (i % step !== 0) continue;
      if (this.visibleClasses && !this.visibleClasses.has(this.cloud.classification[i])) continue;
      if (isolate && this.fpMark[i] !== 1 && this.heroMark[i] !== 1) continue;
      keep.push(i);
    }
    const idx = new Uint32Array(keep);
    this.pointsGeo.setIndex(new THREE.BufferAttribute(idx, 1));
    this.pointsOrbitVisible = keep.length;
    this.emitStatus();
  }

  private pointsOrbitVisible = 0;

  /* ------------------------------------------------------------------ */
  /* Scene geometry                                                       */
  /* ------------------------------------------------------------------ */

  private buildGrid() {
    const c = this.scene.stats.center;
    const size = Math.max(this.scene.stats.span_m[0], this.scene.stats.span_m[1]) + 60;
    this.gridHelper = new THREE.GridHelper(size, 24, 0x2a3142, 0x1b212e);
    this.gridHelper.rotation.x = Math.PI / 2;
    this.gridHelper.position.set(c[0], c[1], 0);
    const mat = this.gridHelper.material as THREE.Material;
    mat.transparent = true;
    mat.opacity = 0.35;
    this.groups.grid.add(this.gridHelper);
  }

  private buildBoundaries() {
    const ringGeo = (ring: number[][], y: number) => {
      const pts = ring.map((p) => new THREE.Vector3(p[0], p[1], y));
      const g = new THREE.BufferGeometry().setFromPoints(pts);
      return g;
    };

    for (const p of this.scene.ground_truth.surrounding_parcels) {
      if (!p.ring.length) continue;
      const line = new THREE.LineLoop(
        ringGeo(p.ring, 0.02),
        new THREE.LineBasicMaterial({ color: 0x4a5568, transparent: true, opacity: 0.5 })
      );
      this.ringLines.push(line);
      this.groups.boundaries.add(line);
    }

    const heroRing = this.scene.ground_truth.parcel_ring;
    for (const y of [0.02, 18.5]) {
      const line = new THREE.LineLoop(
        ringGeo(heroRing, y),
        new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.9 })
      );
      this.heroRingLines.push(line);
      this.groups.boundaries.add(line);
    }
  }

  private buildFootprint() {
    const list: { footprint: number[][]; height_m: number; isHero: boolean }[] = [];
    if (this.scene.ground_truth.footprint.length) {
      list.push({
        footprint: this.scene.ground_truth.footprint,
        height_m: this.scene.ground_truth.height_m,
        isHero: true,
      });
    }
    for (const p of this.scene.ground_truth.surrounding_parcels) {
      if (p.footprint && p.footprint.length) {
        list.push({
          footprint: p.footprint,
          height_m: p.height_m || 14.0,
          isHero: false,
        });
      }
    }

    for (const item of list) {
      const f = item.footprint;
      if (!f.length) continue;

      const geo = new THREE.BufferGeometry().setFromPoints(
        FILL_RING(f, 0.5).map((p) => new THREE.Vector3(p[0], p[1], 0.6))
      );
      const line = new THREE.LineLoop(
        geo,
        new THREE.LineBasicMaterial({
          color: item.isHero ? 0xfbbf24 : 0x38bdf8,
          transparent: true,
          opacity: 0.95,
        })
      );
      this.footprintLines.push(line);
      this.groups.footprint.add(line);

      // Vertical "walls" of the footprint extent — recorded building envelope.
      const h = item.height_m;
      const vz: number[] = [];
      for (let i = 0; i < f.length; i++) {
        const a = f[i];
        const b = f[(i + 1) % f.length];
        vz.push(a[0], a[1], 0.6, a[0], a[1], h);
        vz.push(b[0], b[1], 0.6, b[0], b[1], h);
      }
      const wallGeo = new THREE.BufferGeometry();
      wallGeo.setAttribute('position', new THREE.Float32BufferAttribute(vz, 3));
      const walls = new THREE.LineSegments(
        wallGeo,
        new THREE.LineBasicMaterial({
          color: item.isHero ? 0xfbbf24 : 0x38bdf8,
          transparent: true,
          opacity: 0.3,
        })
      );
      this.groups.footprint.add(walls);
    }
  }

  private buildModel() {
    const list: { footprint: number[][]; height_m: number; isHero: boolean; levels?: any[]; ulpin?: string; code?: string; name?: string }[] = [];
    if (this.scene.ground_truth.footprint.length) {
      list.push({
        footprint: this.scene.ground_truth.footprint,
        height_m: this.scene.ground_truth.height_m,
        isHero: true,
        levels: this.scene.ground_truth.levels,
        ulpin: this.scene.ground_truth.ulpin,
        code: this.scene.ground_truth.building_code,
        name: this.scene.ground_truth.building_name,
      });
    }
    for (const p of this.scene.ground_truth.surrounding_parcels) {
      if (p.footprint && p.footprint.length) {
        list.push({
          footprint: p.footprint,
          height_m: p.height_m || 14.0,
          isHero: false,
          levels: p.levels,
          ulpin: p.ulpin,
          code: p.building_code,
          name: p.building_name,
        });
      }
    }

    for (const b of list) {
      if (!b.footprint.length) continue;

      const shape = new THREE.Shape(b.footprint.map((p) => new THREE.Vector2(p[0], p[1])));
      const extrude = new THREE.ExtrudeGeometry(shape, {
        depth: b.height_m,
        bevelEnabled: false,
      });
      extrude.translate(0, 0, 0.5);
      const mat = new THREE.MeshBasicMaterial({
        color: b.isHero ? 0x60a5fa : 0x818cf8,
        transparent: true,
        opacity: 0.12,
        depthWrite: false,
        side: THREE.DoubleSide,
        wireframe: false,
      });
      const mesh = new THREE.Mesh(extrude, mat);
      mesh.userData = {
        kind: 'reconstruction',
        ulpin: b.ulpin,
        code: b.code,
        name: b.name,
      };
      this.modelMeshes.push(mesh);
      this.groups.model.add(mesh);

      // Edges wireframe.
      const edges = new THREE.EdgesGeometry(extrude);
      const edgeMat = new THREE.LineBasicMaterial({
        color: b.isHero ? 0x60a5fa : 0x818cf8,
        transparent: true,
        opacity: 0.45,
      });
      this.groups.model.add(new THREE.LineSegments(edges, edgeMat));
    }

    const gt = this.scene.ground_truth;
    if (gt.footprint.length >= 3) {
      for (const lv of gt.levels) {
      const planeGeo = new THREE.PlaneGeometry(30, 17);
      const plane = new THREE.Mesh(
        planeGeo,
        new THREE.MeshBasicMaterial({ color: 0x60a5fa, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false })
      );
      plane.position.set(
        (gt.footprint[0][0] + gt.footprint[2][0]) / 2,
        (gt.footprint[0][1] + gt.footprint[2][1]) / 2,
        (lv.min_z + lv.max_z) / 2
      );
      plane.scale.set(
        Math.abs(gt.footprint[2][0] - gt.footprint[0][0]) / 30,
        Math.abs(gt.footprint[2][1] - gt.footprint[0][1]) / 17,
        1
      );
      this.modelMeshes.push(plane);
      this.groups.model.add(plane);
    }
  }

    this.setModelOpacity(0.5);
  }

  setModelOpacity(opacity: number) {
    for (const m of this.modelMeshes) {
      (m.material as THREE.MeshBasicMaterial).opacity = opacity > 0 ? Math.max(0.04, opacity * 0.5) : 0.04;
      (m.material as THREE.MeshBasicMaterial).visible = opacity > 0.01;
    }
  }

  setFloorMarks(level: LidarLevel | null) {
    for (const m of this.floorMarks) {
      this.groups.boundaries.remove(m);
      m.geometry.dispose();
      (m.material as THREE.Material).dispose();
    }
    this.floorMarks = [];
    if (!level) return;
    const f = this.scene.ground_truth.footprint;
    if (!f.length) return;
    const vz: number[] = [];
    for (const y of [level.min_z, level.max_z]) {
      for (let i = 0; i < f.length; i++) {
        const a = f[i];
        const b = f[(i + 1) % f.length];
        vz.push(a[0], a[1], y, b[0], b[1], y);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(vz, 3));
    const marks = new THREE.LineSegments(
      geo,
      new THREE.LineBasicMaterial({ color: 0xf87171, transparent: true, opacity: 0.85 })
    );
    this.floorMarks.push(marks);
    this.groups.boundaries.add(marks);
  }

  private vGuide: THREE.LineSegments | null = null;

  setVerticalGuide(x: number | null, width = 1.2) {
    if (this.vGuide) {
      this.groups.boundaries.remove(this.vGuide);
      this.vGuide.geometry.dispose();
      (this.vGuide.material as THREE.Material).dispose();
      this.vGuide = null;
    }
    if (x == null) return;
    const b = this.scene.stats.bounds;
    const vertical: number[] = [];
    const hw = width / 2;
    // Vertical transparent slab frame across the full scene height at x.
    const ys = [b.min[1], b.max[1]];
    for (const y of ys) {
      for (let i = 0; i < 5; i++) {
        const z0 = b.min[2] + ((b.max[2] - b.min[2]) * i) / 4;
        const z1 = b.min[2] + ((b.max[2] - b.min[2]) * (i + 1)) / 4;
        vertical.push(x - hw, y, z0, x + hw, y, z0);
        vertical.push(x - hw, y, z1, x + hw, y, z1);
        vertical.push(x - hw, y, z0, x - hw, y, z1);
        vertical.push(x + hw, y, z0, x + hw, y, z1);
      }
    }
    for (const z of [b.min[2], b.max[2]]) {
      for (const [y, y2] of [[b.min[1], b.max[1]]]) {
        vertical.push(x - hw, y, z, x + hw, y2, z);
        vertical.push(x + hw, y, z, x - hw, y2, z);
        vertical.push(x - hw, y2, z, x + hw, y2, z);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(vertical, 3));
    const segs = new THREE.LineSegments(
      geo,
      new THREE.LineBasicMaterial({ color: 0x5eead4, transparent: true, opacity: 0.7 })
    );
    this.vGuide = segs;
    this.groups.boundaries.add(segs);
  }

  /* ------------------------------------------------------------------ */
  /* Layers                                                               */
  /* ------------------------------------------------------------------ */

  setLayers(l: LayerVisibility) {
    this.layers = l;
    this.applyVisibility();
  }

  private applyVisibility() {
    this.groups.points.visible = this.layers.lidar;
    this.groups.boundaries.visible = this.layers.parcels;
    this.groups.footprint.visible = this.layers.footprint;
    this.groups.model.visible = this.layers.model;
    this.groups.grid.visible = this.layers.grid;
  }

  /* ------------------------------------------------------------------ */
  /* Point / property picking                                             */
  /* ------------------------------------------------------------------ */

  private pointerDownPos = { x: 0, y: 0, time: 0 };

  onPointerDown = (e: PointerEvent) => {
    this.pointerDownPos = { x: e.clientX, y: e.clientY, time: performance.now() };
  };

  onPointerUp = (e: PointerEvent) => {
    const dist = Math.hypot(e.clientX - this.pointerDownPos.x, e.clientY - this.pointerDownPos.y);
    if (dist > 7) return; // Orbit or pan drag, not a direct click
    const now = performance.now();
    if (now - this.lastClickTime < 35) return;
    this.lastClickTime = now;

    if (this.activeTool === 'measure') {
      const hit = this.pick(e);
      if (hit) this.addMeasurePoint(hit.point);
      return;
    }

    // First try picking point cloud
    const hit = this.pick(e);
    if (hit) {
      this.selectAt(hit.point);
      return;
    }

    // Next try picking 3D building envelope mesh
    const meshHit = this.pickMesh(e);
    if (meshHit) {
      if (meshHit.ulpin) {
        this.cb.onSelectProperty?.(meshHit.ulpin, { x: meshHit.point.x, y: meshHit.point.y, z: meshHit.point.z });
      } else {
        this.selectAt(meshHit.point);
      }
    }
  };

  onDblClick = (e: MouseEvent) => {
    if (this.activeTool !== 'select') return;
    const hit = this.pick(e);
    if (hit) this.cb.onInspectPoint?.(this.inspectInfo(hit.point, hit.index));
  };

  onPointerMove = (e: PointerEvent) => {
    if (performance.now() - this.hoverRaycastTimer < 40) return;
    this.hoverRaycastTimer = performance.now();
    const hit = this.pick(e);
    this.cb.onInspectPoint?.(hit ? this.inspectInfo(hit.point, hit.index) : null);
  };

  private pick(e: PointerEvent | MouseEvent) {
    if (!this.cloud || !this.pointsMesh || !this.pointsGeo) return null;
    const rect = this.container.getBoundingClientRect();
    this.pointerNDC.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointerNDC.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    const idxAttr = this.pointsGeo.getAttribute('aId') as THREE.BufferAttribute;
    if (!idxAttr) return null;

    this.raycaster.setFromCamera(this.pointerNDC, this.camera);
    this.raycaster.params.Points.threshold = 0.8;

    const pts = this.pointsMesh as unknown as THREE.Points;
    const intersect = this.raycaster.intersectObject(pts, false)[0];
    if (!intersect) return null;
    const localIndex = intersect.index != null ? intersect.index : 0;
    // aId maps the (subsampled) buffer position back to the full cloud index.
    const cloudIndex = idxAttr.getX(localIndex);
    const x = this.cloud.positions[cloudIndex * 3];
    const y = this.cloud.positions[cloudIndex * 3 + 1];
    const z = this.cloud.positions[cloudIndex * 3 + 2];
    return { point: new THREE.Vector3(x, y, z), index: cloudIndex };
  }

  private pickMesh(e: PointerEvent | MouseEvent): { point: THREE.Vector3; ulpin?: string; code?: string } | null {
    if (!this.modelMeshes.length) return null;
    const rect = this.container.getBoundingClientRect();
    this.pointerNDC.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointerNDC.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointerNDC, this.camera);
    const hits = this.raycaster.intersectObjects(this.modelMeshes, false);
    if (hits.length > 0) {
      const h = hits[0];
      return {
        point: h.point,
        ulpin: h.object.userData?.ulpin,
        code: h.object.userData?.code,
      };
    }
    return null;
  }

  private selectAt(point: THREE.Vector3) {
    const gt = this.scene.ground_truth;
    const x = point.x;
    const y = point.y;

    if (gt.footprint.length && pointInRing(x, y, gt.footprint)) {
      this.cb.onSelectProperty?.(gt.ulpin, { x, y, z: point.z });
      return;
    }
    if (pointInRing(x, y, gt.parcel_ring)) {
      this.cb.onSelectProperty?.(gt.ulpin, { x, y, z: point.z });
      return;
    }
    for (const p of gt.surrounding_parcels) {
      if (
        (p.footprint && p.footprint.length && pointInRing(x, y, p.footprint)) ||
        (p.ring && p.ring.length && pointInRing(x, y, p.ring))
      ) {
        this.cb.onSelectProperty?.(p.ulpin || (p as any).building_code || (p as any).id || gt.ulpin, { x, y, z: point.z });
        return;
      }
    }
  }

  private inspectInfo(point: THREE.Vector3, idx: number): InspectInfo {
    const cloud = this.cloud!;
    const gt = this.scene.ground_truth;
    const cls = cloud.classification[idx];
    const inHero = pointInRing(point.x, point.y, gt.parcel_ring);
    return {
      x: point.x,
      y: point.y,
      z: point.z,
      classification: cls,
      intensity: cloud.intensity[idx],
      gps: cloud.gps[idx],
      color: `#${new THREE.Color(CLASS_COLORS[cls] || '#8b95a5').getHexString()}`,
      inHeroParcel: inHero,
      ulpin: inHero || pointInRing(point.x, point.y, gt.footprint) ? gt.ulpin : null,
    };
  }

  setActiveTool(tool: 'select' | 'measure') {
    this.activeTool = tool;
    if (tool === 'select') {
      this.measurePts = [];
      this.clearMeasurementVisuals();
    }
  }

  clearMeasurements() {
    this.measurePts = [];
    this.clearMeasurementVisuals();
  }

  private addMeasurePoint(p: THREE.Vector3) {
    const sph = new THREE.Mesh(
      new THREE.SphereGeometry(0.35, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0x38bdf8 })
    );
    sph.position.copy(p);
    this.groups.measure.add(sph);
    this.measureMarkers.push(sph);
    this.measurePts.push(p.clone());
    if (this.measurePts.length >= 2) this.drawMeasurePath();
  }

  private drawMeasurePath() {
    const seg = this.measurePts;
    const pts = seg.slice();
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.9 })
    );
    this.groups.measure.add(line);
    this.measureLines.push(line);

    const dist = seg[0].distanceTo(seg[1]);
    const mid = seg[0].clone().add(seg[1]).multiplyScalar(0.5);
    const el = this.addLabel(this.fmt(dist), mid, 'measure');
    this.measureLabels.push(el);

    if (seg.length === 2) {
      const h = Math.abs(seg[0].z - seg[1].z);
      if (h > 0.001) {
        const midHigh = new THREE.Vector3(seg[1].x, seg[1].y, seg[1].z);
        const elHigh = this.addLabel(`▲ ${this.fmt(h)}`, midHigh.clone().add(new THREE.Vector3(0, 0, 0.8)), 'measure');
        this.measureLabels.push(elHigh);
      }
    }

    this.emitMeasureReads();
  }

  private emitMeasureReads() {
    const reads: MeasureRead[] = [];
    for (let i = 0; i + 1 < this.measurePts.length; i += 2) {
      const d = this.measurePts[i].distanceTo(this.measurePts[i + 1]);
      const h = Math.abs(this.measurePts[i].z - this.measurePts[i + 1].z);
      reads.push({ distance: d, height: h > 0.001 ? h : null });
    }
    this.cb.onMeasure?.(reads);
  }

  private fmt(v: number): string {
    return `${v.toFixed(2)} m`;
  }

  private clearMeasurementVisuals() {
    for (const m of [...this.measureMarkers, ...this.measureLines]) {
      this.groups.measure.remove(m);
      if ((m as THREE.Mesh).geometry) (m as THREE.Mesh).geometry.dispose();
      const mat = (m as THREE.Mesh).material as THREE.Material;
      if (mat) mat.dispose();
    }
    this.measureMarkers = [];
    this.measureLines = [];
    for (const el of this.measureLabels) {
      el.remove();
      this.labelLayer.removeEventListener('pointerdown', () => undefined);
    }
    this.measureLabels.forEach((l) => l.remove());
    this.measureLabels = [];
  }

  /* ------------------------------------------------------------------ */
  /* Labels (DOM, projected each frame)                                   */
  /* ------------------------------------------------------------------ */

  private addLabel(text: string, worldPos: THREE.Vector3, kind: 'property' | 'measure'): HTMLDivElement {
    const el = document.createElement('div');
    el.className = kind === 'property' ? 'lidar-label lidar-label--prop' : 'lidar-label lidar-label--measure';
    el.textContent = text;
    el.style.opacity = '0';
    this.labelLayer.appendChild(el);
    const entry = { el, pos: worldPos.clone() };
    this.labels.push(entry);
    entry.el.addEventListener('pointerdown', (e) => e.stopPropagation());
    return el;
  }

  syncPropertyLabels(items: { text: string; pos: number[] }[]) {
    while (this.labels.length) {
      const l = this.labels.pop();
      if (l) l.el.remove();
    }
    for (const it of items) {
      this.addLabel(it.text, new THREE.Vector3(it.pos[0], it.pos[1], it.pos[2]), 'property');
    }
  }

  private updateLabels() {
    if (!this.labelLayer) return;
    const w = this.container.clientWidth || 1;
    const h = this.container.clientHeight || 1;
    for (const l of this.labels) {
      const v = l.pos.clone().project(this.camera);
      const behind = v.z > 1;
      if (!behind) {
        const x = (v.x * 0.5 + 0.5) * w;
        const y = (-v.y * 0.5 + 0.5) * h;
        l.el.style.transform = `translate(${x.toFixed(0)}px, ${y.toFixed(0)}px) translate(-50%, -110%)`;
        l.el.style.opacity = '1';
      } else {
        l.el.style.opacity = '0';
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* Camera / presets                                                     */
  /* ------------------------------------------------------------------ */

  focusBuilding(sel: LidarSelection | null) {
    if (!sel) {
      this.cameraPreset('fit');
      return;
    }
    const c = this.scene.stats.center;
    const ring = (sel.footprint && sel.footprint.length)
      ? sel.footprint
      : (sel.parcelRing && sel.parcelRing.length ? sel.parcelRing : null);
    const f = ring ? footprintCenter(ring) : [c[0], c[1]];
    const ht = Math.max(12, sel.heightM || 18);

    let maxRadius = 16;
    if (ring) {
      for (const pt of ring) {
        const dist = Math.hypot(pt[0] - f[0], pt[1] - f[1]);
        if (dist > maxRadius) maxRadius = dist;
      }
    }

    const dist = Math.max(28, maxRadius * 2.2, ht * 1.3);
    const tgt = new THREE.Vector3(f[0], f[1], ht * 0.45);
    const pos = new THREE.Vector3(
      f[0] + dist * 0.72,
      f[1] - dist * 0.72,
      Math.max(8, ht * 0.48 + dist * 0.52)
    );
    this.flyTo(pos, tgt);
  }

  cameraPreset(name: CameraPreset) {
    const c = this.scene.stats.center;
    const span = this.scene.stats.span_m;
    const d = (span[0] + span[1]) / 2;
    const h = span[2];
    let pos: number[];
    let tgt: number[];

    switch (name) {
      case 'top':
        pos = [c[0], c[1], c[2] + d * 1.6];
        tgt = [c[0], c[1], c[2]];
        break;
      case 'north': {
        const f = this.scene.ground_truth.footprint.length ? footprintCenter(this.scene.ground_truth.footprint) : [c[0], c[1]];
        pos = [f[0], f[1] - d * 0.9, c[2] + d * 0.45];
        tgt = [f[0], f[1], c[2] + h * 0.35];
        break;
      }
      case 'front': {
        const f = this.scene.ground_truth.footprint.length ? footprintCenter(this.scene.ground_truth.footprint) : [c[0], c[1]];
        pos = [f[0] - d * 0.9, f[1], c[2] + d * 0.45];
        tgt = [f[0], f[1], c[2] + h * 0.35];
        break;
      }
      case 'side': {
        const f = this.scene.ground_truth.footprint.length ? footprintCenter(this.scene.ground_truth.footprint) : [c[0], c[1]];
        pos = [f[0], f[1] + d * 0.9, c[2] + d * 0.45];
        tgt = [f[0], f[1], c[2] + h * 0.35];
        break;
      }
      case 'floor': {
        const f = this.scene.ground_truth.footprint.length ? footprintCenter(this.scene.ground_truth.footprint) : [c[0], c[1]];
        const lv = this.modeOpts.floorLevel || this.scene.ground_truth.levels[Math.floor(this.scene.ground_truth.levels.length / 2)];
        const zc = (lv ? (lv.min_z + lv.max_z) / 2 : c[2]);
        pos = [f[0] + d * 0.5, f[1] - d * 0.5, zc + d * 0.8];
        tgt = [f[0], f[1], zc];
        break;
      }
      case 'building': {
        const sel = this.modeOpts?.selection;
        if (sel) {
          this.focusBuilding(sel);
          return;
        }
        const f = this.scene.ground_truth.footprint.length ? footprintCenter(this.scene.ground_truth.footprint) : [c[0], c[1]];
        const ht = this.scene.ground_truth.height_m || 18;
        this.flyTo(new THREE.Vector3(f[0] + 35, f[1] - 35, ht * 0.5 + 28), new THREE.Vector3(f[0], f[1], ht * 0.45));
        return;
      }
      case 'fit':
      default:
        pos = [c[0] + d * 0.7, c[1] - d * 0.7, c[2] + d * 0.55];
        tgt = [c[0], c[1], c[2]];
        break;
    }

    this.flyTo(new THREE.Vector3(pos[0], pos[1], pos[2]), new THREE.Vector3(tgt[0], tgt[1], tgt[2]));
  }

  private flyTo(pos: THREE.Vector3, tgt: THREE.Vector3) {
    this.camAnim = {
      t0: performance.now(),
      dur: 900,
      fromPos: this.camera.position.clone(),
      toPos: pos,
      fromTarget: this.controls.target.clone(),
      toTarget: tgt,
    };
  }

  /* ------------------------------------------------------------------ */
  /* Status / loop                                                        */
  /* ------------------------------------------------------------------ */

  private emitStatus() {
    this.cb.onStatus?.({
      fps: 0,
      rendered: this.pointsOrbitVisible,
      memoryMB: 0,
    });
  }

  private tick = () => {
    if (this.disposed) return;
    this.raf = requestAnimationFrame(this.tick);
    const now = performance.now();

    this.frameCount++;
    if (now - this.lastFpsEmit > 1000) {
      this.cb.onStatus?.({
        fps: Math.round(this.frameCount / Math.max(1, (now - this.lastFpsEmit) / 1000)),
        rendered: this.pointsOrbitVisible,
        memoryMB: Math.round((performance as any).memory?.usedJSHeapSize / 1048576) || 0,
      });
      this.frameCount = 0;
      this.lastFpsEmit = now;
    }

    if (this.camAnim) {
      const a = this.camAnim;
      const t = Math.min(1, (now - a.t0) / a.dur);
      const k = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      this.camera.position.lerpVectors(a.fromPos, a.toPos, k);
      this.controls.target.lerpVectors(a.fromTarget, a.toTarget, k);
      if (t >= 1) this.camAnim = null;
    }

    this.controls.update();
    this.updateLabels();
    this.renderer.render(this.scene3d, this.camera);
  };

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.resizeObs?.disconnect();

    const canvas = this.renderer.domElement;
    canvas.removeEventListener('pointerdown', this.onPointerDown);
    canvas.removeEventListener('pointerup', this.onPointerUp);
    canvas.removeEventListener('pointermove', this.onPointerMove);
    canvas.removeEventListener('dblclick', this.onDblClick);

    this.controls.dispose();
    for (const g of Object.values(this.groups)) {
      g.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        const mat = mesh.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else if (mat) mat.dispose();
      });
    }
    this.pointsGeo?.dispose();
    if (this.pointsMat) {
      Object.values(this.pointsMat.uniforms).forEach((u) => {
        if (u.value instanceof THREE.Texture) u.value.dispose();
      });
      this.pointsMat.dispose();
    }
    this.renderer.dispose();
    if (this.renderer.domElement.parentElement === this.container) {
      this.container.removeChild(this.renderer.domElement);
    }
    for (const l of this.labels) l.el.remove();
    this.labels = [];
  }
}

function FILL_RING(ring: number[][], eps: number): number[][] {
  const minX = Math.min(...ring.map((p) => p[0])) - eps;
  const minY = Math.min(...ring.map((p) => p[1])) - eps;
  const maxX = Math.max(...ring.map((p) => p[0])) + eps;
  const maxY = Math.max(...ring.map((p) => p[1])) + eps;
  return [
    [minX, minY],
    [maxX, minY],
    [maxX, maxY],
    [minX, maxY],
  ];
}

function footprintCenter(f: number[][]): [number, number] {
  let x = 0;
  let y = 0;
  for (const p of f) {
    x += p[0];
    y += p[1];
  }
  return [x / f.length, y / f.length];
}

export default PointCloudEngine;