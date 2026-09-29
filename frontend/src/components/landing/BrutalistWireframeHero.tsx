import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

interface Props {
  wireColor?: string;
  className?: string;
  onExploreClick?: () => void;
  isLightMode?: boolean;
}

export const BrutalistWireframeHero: React.FC<Props> = ({
  wireColor: _wireColor = '#00ff66',
  className = '',
  onExploreClick,
  isLightMode = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [wireMode, setWireMode] = useState<'ELECTRIC_LIME' | 'SIGNAL_CYAN' | 'TACTICAL_AMBER'>('ELECTRIC_LIME');
  const [activePreset, setActivePreset] = useState<'ISOMETRIC' | 'TOP_DOWN' | 'STREET' | 'SECTION'>('ISOMETRIC');
  const [constructionPhase, setConstructionPhase] = useState<number>(0);
  const [telemetry, setTelemetry] = useState({
    yaw: 42.5,
    pitch: 28.1,
    altitude: 18.0,
    fps: 60,
    nodes: 840,
    activeFloor: 'L03',
  });

  const colorHex = isLightMode
    ? 0x0a0a0a
    : wireMode === 'ELECTRIC_LIME' ? 0x00ff66 : wireMode === 'SIGNAL_CYAN' ? 0x00f0ff : 0xffaa00;
  const accentHexStr = isLightMode
    ? '#00e55b'
    : wireMode === 'ELECTRIC_LIME' ? '#00ff66' : wireMode === 'SIGNAL_CYAN' ? '#00f0ff' : '#ffaa00';

  // #00e55b is a fill, not a text colour: on paper it only reaches 1.5:1.
  // Text uses the darker step of the same ramp, matching --accent-strong in
  // the app tokens. The wireframe itself keeps the bright one.
  const accentTextStr = isLightMode
    ? '#00732d'
    : wireMode === 'ELECTRIC_LIME' ? '#00ff66' : wireMode === 'SIGNAL_CYAN' ? '#00f0ff' : '#ffaa00';

  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);

  // Switch camera views
  const applyPreset = useCallback((preset: 'ISOMETRIC' | 'TOP_DOWN' | 'STREET' | 'SECTION') => {
    setActivePreset(preset);
    const cam = cameraRef.current;
    const ctrl = controlsRef.current;
    if (!cam || !ctrl) return;

    if (preset === 'ISOMETRIC') {
      cam.position.set(45, 36, 50);
      ctrl.target.set(0, 9, 0);
    } else if (preset === 'TOP_DOWN') {
      cam.position.set(0.1, 75, 0.1);
      ctrl.target.set(0, 0, 0);
    } else if (preset === 'STREET') {
      cam.position.set(0, 3.2, 38);
      ctrl.target.set(0, 9, 0);
    } else if (preset === 'SECTION') {
      cam.position.set(55, 10, 0);
      ctrl.target.set(0, 9, 0);
    }
    ctrl.update();
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 550;

    // 1. Scene
    const bgHex = isLightMode ? 0xf4f3ee : 0x060709;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(bgHex);
    scene.fog = new THREE.FogExp2(bgHex, 0.0075);

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 1000);
    camera.position.set(45, 36, 50);
    cameraRef.current = camera;

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    // 4. Orbit Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 - 0.02; // Always stay strictly above ground!
    controls.minDistance = 15;
    controls.maxDistance = 150;
    controls.target.set(0, 9, 0);
    controlsRef.current = controls;

    // 5. Constructing Coordinate Grid
    const gridHelper = new THREE.GridHelper(
      120,
      60,
      isLightMode ? 0x0a0a0a : colorHex,
      isLightMode ? 0xd0cebe : 0x1e2530
    );
    gridHelper.position.y = 0;
    scene.add(gridHelper);

    // Secondary fine subdivisions
    const subGrid = new THREE.GridHelper(120, 120, isLightMode ? 0xe2dfd2 : 0x0e131b, isLightMode ? 0xebe9dd : 0x0a0e14);
    subGrid.position.y = -0.05;
    scene.add(subGrid);

    // Coordinate crosshairs
    const axisGroup = new THREE.Group();
    const axisMat = new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: 0.25 });
    axisGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-60, 0.05, 0), new THREE.Vector3(60, 0.05, 0)]), axisMat));
    axisGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0.05, -60), new THREE.Vector3(0, 0.05, 60)]), axisMat));
    scene.add(axisGroup);

    // 6. Real-time Node Particle Field (Constructing lattice)
    const nodeCount = 350;
    const nodeGeo = new THREE.BufferGeometry();
    const nodePos = new Float32Array(nodeCount * 3);
    for (let i = 0; i < nodeCount; i++) {
      nodePos[i * 3] = (Math.random() - 0.5) * 100;
      nodePos[i * 3 + 1] = Math.random() * 25;
      nodePos[i * 3 + 2] = (Math.random() - 0.5) * 100;
    }
    nodeGeo.setAttribute('position', new THREE.BufferAttribute(nodePos, 3));
    const nodeMat = new THREE.PointsMaterial({
      color: colorHex,
      size: 1.2,
      transparent: true,
      opacity: 0.45,
    });
    const nodePoints = new THREE.Points(nodeGeo, nodeMat);
    scene.add(nodePoints);

    // 7. Hero Building B-17 (Center Volumetric Wireframe)
    const heroFloors = 5;
    const floorHeight = 3.6;
    const b17W = 14;
    const b17D = 10;
    const totalHeight = heroFloors * floorHeight;

    const heroGroup = new THREE.Group();
    scene.add(heroGroup);

    // Building B-17 Outer Edges
    const heroBoxGeo = new THREE.BoxGeometry(b17W, totalHeight, b17D);
    const heroEdges = new THREE.EdgesGeometry(heroBoxGeo);
    const heroWireMat = new THREE.LineBasicMaterial({ color: colorHex, linewidth: 2 });
    const heroWire = new THREE.LineSegments(heroEdges, heroWireMat);
    heroWire.position.y = totalHeight / 2;
    heroGroup.add(heroWire);

    // Translucent X-Ray body
    const heroSolidMat = new THREE.MeshBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: 0.04,
      wireframe: false,
    });
    const heroSolid = new THREE.Mesh(heroBoxGeo, heroSolidMat);
    heroSolid.position.y = totalHeight / 2;
    heroGroup.add(heroSolid);

    // Stratified Floor Slabs
    const slabs: THREE.LineSegments[] = [];
    for (let f = 1; f < heroFloors; f++) {
      const slabEdges = new THREE.EdgesGeometry(new THREE.PlaneGeometry(b17W, b17D));
      const slab = new THREE.LineSegments(slabEdges, new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: 0.7 }));
      slab.rotation.x = Math.PI / 2;
      slab.position.y = f * floorHeight;
      heroGroup.add(slab);
      slabs.push(slab);
    }

    // Subterranean Basement B1 (Underground Solid Wireframe)
    const b1Geo = new THREE.BoxGeometry(b17W + 2, floorHeight, b17D + 2);
    const b1Edges = new THREE.EdgesGeometry(b1Geo);
    const b1Wire = new THREE.LineSegments(b1Edges, new THREE.LineBasicMaterial({ color: 0xef4444, transparent: true, opacity: 0.6 }));
    b1Wire.position.y = -floorHeight / 2;
    heroGroup.add(b1Wire);

    // Subsurface utility warning ring
    const pipeGeo = new THREE.RingGeometry(11, 11.4, 32);
    const pipeWire = new THREE.LineLoop(pipeGeo, new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.4 }));
    pipeWire.rotation.x = Math.PI / 2;
    pipeWire.position.set(0, -1.8, 0);
    heroGroup.add(pipeWire);

    // 8. Surrounding Precinct Wireframe Buildings (7 Precinct Towers)
    const precinctGroup = new THREE.Group();
    scene.add(precinctGroup);

    const precinctSpecs = [
      { x: -28, z: -24, w: 10, d: 10, h: 22, code: 'B-01' },
      { x: -30, z: 18, w: 12, d: 8, h: 16, code: 'B-02' },
      { x: 26, z: -26, w: 10, d: 12, h: 32, code: 'B-03' }, // High-rise
      { x: 30, z: 20, w: 14, d: 10, h: 14, code: 'B-04' },
      { x: -8, z: -35, w: 16, d: 8, h: 12, code: 'B-05' },
      { x: 32, z: -4, w: 8, d: 12, h: 20, code: 'B-06' },
      { x: -26, z: -4, w: 8, d: 8, h: 10, code: 'B-07' },
    ];

    precinctSpecs.forEach((spec) => {
      const bGeo = new THREE.BoxGeometry(spec.w, spec.h, spec.d);
      const bEdges = new THREE.EdgesGeometry(bGeo);
      const bWire = new THREE.LineSegments(
        bEdges,
        new THREE.LineBasicMaterial({ color: 0x475569, transparent: true, opacity: 0.45 })
      );
      bWire.position.set(spec.x, spec.h / 2, spec.z);
      precinctGroup.add(bWire);
    });

    // 9. Oscillating Laser Radar Scanline Plane
    const scanGeo = new THREE.PlaneGeometry(b17W + 8, b17D + 8);
    const scanEdges = new THREE.EdgesGeometry(scanGeo);
    const scanWire = new THREE.LineSegments(
      scanEdges,
      new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: 0.9 })
    );
    scanWire.rotation.x = Math.PI / 2;
    scanWire.position.y = 0;
    heroGroup.add(scanWire);

    // Semi-transparent laser plane
    const scanPlane = new THREE.Mesh(
      scanGeo,
      new THREE.MeshBasicMaterial({ color: colorHex, transparent: true, opacity: 0.08, side: THREE.DoubleSide })
    );
    scanPlane.rotation.x = Math.PI / 2;
    scanPlane.position.y = 0;
    heroGroup.add(scanPlane);

    // 10. Animation Loop & Construction Sequence
    let animationFrameId: number;
    let clock = new THREE.Clock();
    let frameCount = 0;
    let lastFpsCheck = performance.now();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const time = clock.getElapsedTime();

      // Progressive construction reveal on load
      if (time < 1.0) {
        setConstructionPhase(1); // Nodes appearing
        heroGroup.scale.set(0.1, 0.1, 0.1);
        precinctGroup.scale.set(0.1, 0.1, 0.1);
      } else if (time < 2.2) {
        setConstructionPhase(2); // Grid & geometry rising
        const progress = (time - 1.0) / 1.2;
        heroGroup.scale.set(progress, progress, progress);
        precinctGroup.scale.set(0.2, 0.2, 0.2);
      } else if (time < 3.2) {
        setConstructionPhase(3); // Full precinct extrusion
        heroGroup.scale.set(1, 1, 1);
        const pProgress = (time - 2.2) / 1.0;
        precinctGroup.scale.set(pProgress, pProgress, pProgress);
      } else {
        setConstructionPhase(4); // Fully operational
        heroGroup.scale.set(1, 1, 1);
        precinctGroup.scale.set(1, 1, 1);
      }

      // Slow majestic rotation of precinct
      heroGroup.rotation.y = time * 0.04;
      precinctGroup.rotation.y = time * 0.04;

      // Laser radar scanline oscillates vertically (0 to 18m)
      const scanY = (Math.sin(time * 1.5) * 0.5 + 0.5) * (totalHeight + 1);
      scanWire.position.y = scanY;
      scanPlane.position.y = scanY;

      // Subtle float of background nodes
      nodePoints.rotation.y = time * 0.01;

      // Calculate telemetry
      frameCount++;
      const now = performance.now();
      if (now - lastFpsCheck >= 500) {
        const curFps = Math.round((frameCount * 1000) / (now - lastFpsCheck));
        frameCount = 0;
        lastFpsCheck = now;
        const fl = Math.floor(scanY / floorHeight);
        setTelemetry({
          yaw: Number((camera.position.x * 1.8).toFixed(1)),
          pitch: Number((camera.position.y * 1.2).toFixed(1)),
          altitude: Number(scanY.toFixed(1)),
          fps: Math.min(curFps, 60),
          nodes: 840,
          activeFloor: fl <= 0 ? 'B01' : fl === 1 ? 'GRD' : `L0${fl}`,
        });
      }

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    // 11. Resize Observer
    const handleResize = () => {
      if (!container) return;
      const w = container.clientWidth || 800;
      const h = container.clientHeight || 550;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);
      controls.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [colorHex]);

  return (
    <div
      className={`relative w-full h-full min-h-[480px] lg:min-h-[580px] ${
        isLightMode
          ? 'bg-[#F4F3EE] border-2 border-black text-black'
          : 'bg-[#060709] border-2 border-white/20 text-white'
      } select-none overflow-hidden ${className}`}
    >
      {/* 3D Canvas Container */}
      <div ref={containerRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Top Left HUD: System Status & Construction Stage */}
      <div className="absolute top-4 left-4 z-10 pointer-events-none font-mono text-[11px] space-y-1">
        <div
          className={`flex items-center gap-2 backdrop-blur px-3 py-1.5 ${
            isLightMode
              ? 'bg-white/95 text-black border-2 border-black shadow-[3px_3px_0px_0px_#000]'
              : 'bg-black/80 text-white border border-white/20'
          }`}
        >
          <span className="w-2 h-2 rounded-full animate-ping" style={{ backgroundColor: accentHexStr }} />
          <span className="font-bold tracking-wider">BHU-DRISHTI // 3D-ULPIN CORE</span>
          <span aria-hidden="true" className={isLightMode ? 'text-black/30' : 'text-white/70'}>
            |
          </span>
          <span className={`text-[10px] ${isLightMode ? 'text-black/70' : 'text-white/70'}`}>
            PHASE 0{constructionPhase}/04
          </span>
        </div>
        <div
          className={`text-[10px] px-2.5 py-1 w-fit ${
            isLightMode
              ? 'bg-white text-black/70 border border-black'
              : 'bg-black/60 text-white/75 border border-white/10'
          }`}
        >
          TARGET: SHREE GANESH CHS (B-17) // CTS 142/A
        </div>
      </div>

      {/* Top Right HUD: Live Telemetry & Coordinate Ticker */}
      <div className="absolute top-4 right-4 z-10 pointer-events-none font-mono text-[10px] text-right space-y-1 hidden sm:block">
        <div
          className={`backdrop-blur px-3 py-1.5 inline-block ${
            isLightMode
              ? 'bg-white/95 text-black border-2 border-black shadow-[3px_3px_0px_0px_#000]'
              : 'bg-black/80 text-white border border-white/20'
          }`}
        >
          <div className="flex items-center gap-3">
            <span>
              FPS: <strong style={{ color: accentTextStr }}>{telemetry.fps}</strong>
            </span>
            <span aria-hidden="true" className={isLightMode ? 'text-black/20' : 'text-white/65'}>
                |
              </span>
            <span>
              NODES: <strong>{telemetry.nodes}</strong>
            </span>
            <span aria-hidden="true" className={isLightMode ? 'text-black/20' : 'text-white/65'}>
                |
              </span>
            <span>
              STRATUM: <strong style={{ color: accentTextStr }}>{telemetry.activeFloor}</strong>
            </span>
          </div>
        </div>
        <div
          className={`text-[9px] px-2 py-0.5 w-fit ml-auto ${
            isLightMode
              ? 'bg-white text-black/60 border border-black'
              : 'bg-black/60 text-white/75 border border-white/10'
          }`}
        >
          RADAR ALT: {telemetry.altitude}M GTS
        </div>
      </div>

      {/* Bottom Center: Camera View Presets */}
      <div
        className={`absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 backdrop-blur p-1.5 text-[10px] font-mono shadow-2xl ${
          isLightMode ? 'bg-white/95 border-2 border-black shadow-[3px_3px_0px_0px_#000]' : 'bg-black/85 border-2 border-white/20'
        }`}
      >
        {(['ISOMETRIC', 'TOP_DOWN', 'STREET', 'SECTION'] as const).map((preset) => (
          <button
            key={preset}
            onClick={() => applyPreset(preset)}
            className={`px-3 py-1.5 uppercase font-bold transition ${
              activePreset === preset
                ? isLightMode
                  ? 'bg-black text-white shadow-xs'
                  : 'bg-white text-black'
                : isLightMode
                ? 'text-black/70 hover:text-black hover:bg-neutral-100'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            {preset.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Bottom Left: Theme Accent Swatch */}
      <div
        className={`absolute bottom-4 left-4 z-10 hidden md:flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-mono ${
          isLightMode ? 'bg-white border-2 border-black text-black' : 'bg-black/80 border border-white/20 text-white'
        }`}
      >
        <span className={isLightMode ? 'text-black/70' : 'text-white/75'}>PALETTE:</span>
        <button
          onClick={() => setWireMode('ELECTRIC_LIME')}
          className={`w-3 h-3 rounded-full border ${wireMode === 'ELECTRIC_LIME' ? (isLightMode ? 'ring-2 ring-black' : 'ring-2 ring-white') : ''}`}
          style={{ backgroundColor: '#00ff66' }}
          title="Electric Lime"
        />
        <button
          onClick={() => setWireMode('SIGNAL_CYAN')}
          className={`w-3 h-3 rounded-full border ${wireMode === 'SIGNAL_CYAN' ? (isLightMode ? 'ring-2 ring-black' : 'ring-2 ring-white') : ''}`}
          style={{ backgroundColor: '#00f0ff' }}
          title="Signal Cyan"
        />
        <button
          onClick={() => setWireMode('TACTICAL_AMBER')}
          className={`w-3 h-3 rounded-full border ${wireMode === 'TACTICAL_AMBER' ? (isLightMode ? 'ring-2 ring-black' : 'ring-2 ring-white') : ''}`}
          style={{ backgroundColor: '#ffaa00' }}
          title="Tactical Amber"
        />
      </div>

      {/* Bottom Right: Direct Workspace Launch Action */}
      {onExploreClick && (
        <button
          onClick={onExploreClick}
          className={`absolute bottom-4 right-4 z-10 px-4 py-2 text-xs font-mono font-black uppercase tracking-wider transition shadow-lg flex items-center gap-2 cursor-pointer ${
            isLightMode
              ? 'bg-black text-white hover:bg-[#00e55b] hover:text-black border-2 border-black shadow-[3px_3px_0px_0px_#000]'
              : 'bg-white text-black hover:bg-[#00ff66]'
          }`}
        >
          <span>INTERROGATE B-17</span>
          <span>→</span>
        </button>
      )}

      {/* Corner Crosshair Reticles */}
      <div className={`absolute top-2 left-2 text-[10px] font-mono pointer-events-none ${isLightMode ? 'text-black/65' : 'text-white/65'}`}>+ 00.00</div>
      <div className={`absolute top-2 right-2 text-[10px] font-mono pointer-events-none ${isLightMode ? 'text-black/65' : 'text-white/65'}`}>+ 99.99</div>
      <div className={`absolute bottom-2 left-2 text-[10px] font-mono pointer-events-none ${isLightMode ? 'text-black/65' : 'text-white/65'}`}>+ 19.15°N</div>
      <div className={`absolute bottom-2 right-2 text-[10px] font-mono pointer-events-none ${isLightMode ? 'text-black/65' : 'text-white/65'}`}>+ 72.99°E</div>
    </div>
  );
};
