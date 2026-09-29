import React, { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { useApp } from '../../context/AppContext';

interface Props {
  map: maplibregl.Map | null;
  /** Camera pitch in degrees. The dot is dropped from the camera's own tilt. */
  pitch?: number;
  /** Called once the pointer has been placed, so the caller can gate the flyTo. */
  onPlaced?: () => void;
}

/**
 * The pulsing red dot that lands on whatever Ask-The-Map just highlighted.
 *
 * Ask-The-Map returns a `focus_point` in the 3D studio's local scene
 * coordinates, and the 2D views previously had no way to act on it -- the
 * query set state, showed "Highlight applied to the 3D view", and left both
 * 2D maps sitting wherever they were. Worse, the focus point is not a
 * longitude, so naively handing it to `flyTo` would send the camera to
 * longitude 160 east, which is the middle of the Pacific.
 *
 * So the point is converted through the same local-to-geo transform the
 * cadastral atlas already uses for its demo geometry: Airoli is the anchor at
 * scene (160, 152.5) and each scene unit is 9e-6 degrees. North is scene -y,
 * hence the sign flip on latitude.
 *
 * The marker element is a div rather than a symbol layer because it has to
 * animate with CSS and sit above the raster, and because a Marker is removed
 * and re-added cleanly when the query changes.
 */
export const HighlightPointer: React.FC<Props> = ({ map, pitch = 0, onPlaced }) => {
  const { highlight } = useApp();
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const pingRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!map) return;

    const focus = highlight?.focusPoint;
    if (!focus) {
      markerRef.current?.remove();
      markerRef.current = null;
      pingRef.current = null;
      return;
    }

    const [lng, lat] = localToGeo(focus);
    const color = highlight.color || '#EF4444';

    // Drop the old marker before placing the new one so repeated queries do
    // not stack dots on top of each other.
    markerRef.current?.remove();
    markerRef.current = null;

    const wrap = document.createElement('div');
    wrap.className = 'relative flex items-center justify-center';
    wrap.style.width = '20px';
    wrap.style.height = '20px';

    // Expanding ring. The pulse is a CSS animation on a child rather than on
    // the marker itself so that re-adding the marker restarts it; a marker
    // reused across queries would otherwise keep whatever animation state it
    // had when the previous query finished.
    const ping = document.createElement('div');
    ping.className = 'absolute inset-0 rounded-full animate-ping pointer-events-none';
    ping.style.backgroundColor = color;
    ping.style.opacity = '0.45';
    pingRef.current = ping;
    wrap.appendChild(ping);

    const dot = document.createElement('div');
    dot.className = 'w-5 h-5 rounded-full border-2 border-white shadow-xl cursor-pointer';
    dot.style.backgroundColor = color;
    dot.title = highlight.label || 'Highlighted feature';
    wrap.appendChild(dot);

    const marker = new maplibregl.Marker({ element: wrap, anchor: 'center' })
      .setLngLat([lng, lat])
      .addTo(map);
    markerRef.current = marker;

    map.flyTo({
      center: [lng, lat],
      zoom: Math.max(map.getZoom(), 17),
      pitch,
      duration: 1400,
      essential: true,
    });
    onPlaced?.();

    return () => {
      marker.remove();
      pingRef.current = null;
    };
  }, [map, highlight, pitch, onPlaced]);

  return null;
};

/**
 * Local scene coordinates to WGS84, matching the transform the cadastral atlas
 * uses for its demo buildings: scene x grows east, scene y grows south, and
 * Airoli sits at scene (160, 152.5).
 */
export const AIROLI_CENTER: [number, number] = [72.9984, 19.1557];
const SCENE_SCALE = 0.000009;
const SCENE_ANCHOR: [number, number] = [160, 152.5];

export function localToGeo(point: [number, number]): [number, number] {
  return [
    AIROLI_CENTER[0] + (point[0] - SCENE_ANCHOR[0]) * SCENE_SCALE,
    AIROLI_CENTER[1] - (point[1] - SCENE_ANCHOR[1]) * SCENE_SCALE,
  ];
}
