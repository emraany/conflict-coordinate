import { useEffect, useMemo, useRef } from "react";
import GlobeGL from "react-globe.gl";
import type { GlobeMethods } from "react-globe.gl";

import { colors, statusColor } from "../styles/tokens";
import type { CrisisListItem } from "../types";

interface Props {
  crises: CrisisListItem[];
  onSelect: (slug: string) => void;
  selectedSlug: string | null;
}

interface PointDatum extends CrisisListItem {
  __color: string;
}

interface RingDatum {
  lat: number;
  lng: number;
  maxRadius: number;
  propagationSpeed: number;
  repeatPeriod: number;
}

export function Globe({ crises, onSelect, selectedSlug }: Props) {
  const ref = useRef<GlobeMethods | undefined>(undefined);

  const points: PointDatum[] = useMemo(
    () =>
      crises.map((c) => ({
        ...c,
        __color: statusColor(c.status),
      })),
    [crises],
  );

  const rings: RingDatum[] = useMemo(
    () =>
      crises
        .filter((c) => c.status === "active")
        .map((c) => ({
          lat: c.lat,
          lng: c.lng,
          maxRadius: 4,
          propagationSpeed: 2,
          repeatPeriod: 2000,
        })),
    [crises],
  );

  useEffect(() => {
    const g = ref.current;
    if (!g) return;
    // Slow auto-rotate on the orb for ambient motion.
    const controls = g.controls() as {
      autoRotate: boolean;
      autoRotateSpeed: number;
      enableZoom: boolean;
    };
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.25;
    controls.enableZoom = true;
    g.pointOfView({ altitude: 2.4 }, 0);
  }, []);

  useEffect(() => {
    const g = ref.current;
    if (!g || !selectedSlug) return;
    const target = crises.find((c) => c.slug === selectedSlug);
    if (!target) return;
    g.pointOfView({ lat: target.lat, lng: target.lng, altitude: 1.6 }, 900);
  }, [selectedSlug, crises]);

  return (
    <GlobeGL
      ref={ref}
      backgroundColor="rgba(0,0,0,0)"
      globeImageUrl="//unpkg.com/three-globe/example/img/earth-dark.jpg"
      bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
      showAtmosphere={true}
      atmosphereColor={colors.amber}
      atmosphereAltitude={0.18}
      pointsData={points}
      pointLat={(d) => (d as PointDatum).lat}
      pointLng={(d) => (d as PointDatum).lng}
      pointColor={(d) => (d as PointDatum).__color}
      pointAltitude={0.012}
      pointRadius={0.35}
      pointsMerge={false}
      pointLabel={(d) => {
        const p = d as PointDatum;
        return `<div style="
          font-family: 'IBM Plex Mono', monospace;
          background: ${colors.bgRaised};
          color: ${colors.text};
          border: 1px solid ${colors.ruleStrong};
          padding: 6px 10px;
          font-size: 11px;
          letter-spacing: 0.08em;
        ">
          <div style="color:${p.__color};font-size:10px;letter-spacing:0.2em;">[ ${p.status.toUpperCase()} ]</div>
          <div style="margin-top:2px;">${p.name}</div>
          <div style="color:${colors.textMuted};font-size:10px;margin-top:2px;">${p.country ?? ""}</div>
        </div>`;
      }}
      onPointClick={(p) => onSelect((p as PointDatum).slug)}
      ringsData={rings}
      ringLat={(d) => (d as RingDatum).lat}
      ringLng={(d) => (d as RingDatum).lng}
      ringMaxRadius={(d) => (d as RingDatum).maxRadius}
      ringPropagationSpeed={(d) => (d as RingDatum).propagationSpeed}
      ringRepeatPeriod={(d) => (d as RingDatum).repeatPeriod}
      ringColor={() => colors.active}
    />
  );
}
