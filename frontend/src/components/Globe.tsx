import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import GlobeGL from "react-globe.gl";
import type { GlobeMethods } from "react-globe.gl";

import { colors, fonts, space, statusColor } from "../styles/tokens";
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

type TextureMode = "color" | "mono";

const COLOR_TEXTURE = "//unpkg.com/three-globe/example/img/earth-blue-marble.jpg";
const BUMP_TEXTURE = "//unpkg.com/three-globe/example/img/earth-topology.png";

const LS_TEXTURE = "cc.globe.texture";
const LS_AUTOROTATE = "cc.globe.autoRotate";

function readLocal<T extends string>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  const v = window.localStorage.getItem(key);
  return (v as T) ?? fallback;
}

function makeMonoDataUrl(
  sourceUrl: string,
  onReady: (dataUrl: string) => void,
) {
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(img, 0, 0);
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const d = data.data;
    for (let i = 0; i < d.length; i += 4) {
      const gray = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      const boosted = Math.max(0, Math.min(255, gray * 1.3 + 10));
      d[i] = boosted;
      d[i + 1] = boosted;
      d[i + 2] = boosted;
    }
    ctx.putImageData(data, 0, 0);
    onReady(canvas.toDataURL("image/jpeg", 0.9));
  };
  img.src = sourceUrl;
}

function GlobeControlChips({
  textureMode,
  autoRotate,
  onToggleTexture,
  onToggleAutoRotate,
  onResetView,
}: {
  textureMode: TextureMode;
  autoRotate: boolean;
  onToggleTexture: () => void;
  onToggleAutoRotate: () => void;
  onResetView: () => void;
}) {
  const chipStyle = {
    background: colors.bgRaised,
    border: `1px solid ${colors.rule}`,
    color: colors.textMuted,
    fontFamily: fonts.mono,
    fontSize: 10,
    letterSpacing: "0.18em",
    padding: "6px 10px",
    cursor: "pointer",
    textTransform: "uppercase" as const,
  };
  return (
    <div
      style={{
        position: "absolute",
        right: space.md,
        bottom: space.md,
        display: "flex",
        gap: space.sm,
        zIndex: 2,
      }}
    >
      <button
        type="button"
        onClick={onToggleTexture}
        style={{
          ...chipStyle,
          color: textureMode === "color" ? colors.oliveLight : colors.textMuted,
        }}
        title="Toggle between realistic and mono textures"
      >
        [ {textureMode === "color" ? "COLOR" : "MONO"} ]
      </button>
      <button
        type="button"
        onClick={onToggleAutoRotate}
        style={{
          ...chipStyle,
          color: autoRotate ? colors.oliveLight : colors.textMuted,
        }}
        title="Toggle auto-rotation"
      >
        [ AUTO {autoRotate ? "ON" : "OFF"} ]
      </button>
      <button
        type="button"
        onClick={onResetView}
        style={chipStyle}
        title="Reset camera to default"
      >
        [ RESET ]
      </button>
    </div>
  );
}

export function Globe({ crises, onSelect, selectedSlug }: Props) {
  const ref = useRef<GlobeMethods | undefined>(undefined);
  const monoDataUrlRef = useRef<string | null>(null);

  const [textureMode, setTextureMode] = useState<TextureMode>(() =>
    readLocal<TextureMode>(LS_TEXTURE, "color"),
  );
  const [autoRotate, setAutoRotate] = useState<boolean>(
    () => readLocal(LS_AUTOROTATE, "false") === "true",
  );
  const [activeTextureUrl, setActiveTextureUrl] = useState<string>(COLOR_TEXTURE);

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

  // Apply OrbitControls tuning once.
  useEffect(() => {
    const g = ref.current;
    if (!g) return;
    const c = g.controls() as any;
    c.enablePan = true;
    c.enableDamping = true;
    c.dampingFactor = 0.12;
    c.rotateSpeed = 0.6;
    c.zoomSpeed = 0.8;
    c.panSpeed = 0.6;
    c.minDistance = 180;
    c.maxDistance = 600;
    c.enableKeys = true;
    c.keyPanSpeed = 18;
    c.screenSpacePanning = false;
    g.pointOfView({ lat: 20, lng: 0, altitude: 2.4 }, 0);
  }, []);

  // Sync auto-rotate state to OrbitControls + localStorage.
  useEffect(() => {
    const g = ref.current;
    if (!g) return;
    const c = g.controls() as any;
    c.autoRotate = autoRotate;
    c.autoRotateSpeed = 0.25;
    window.localStorage.setItem(LS_AUTOROTATE, String(autoRotate));
  }, [autoRotate]);

  // Fly to selected crisis.
  useEffect(() => {
    const g = ref.current;
    if (!g || !selectedSlug) return;
    const target = crises.find((c) => c.slug === selectedSlug);
    if (!target) return;
    g.pointOfView({ lat: target.lat, lng: target.lng, altitude: 1.6 }, 900);
  }, [selectedSlug, crises]);

  // Switch texture by updating the globeImageUrl prop (no THREE access needed).
  useEffect(() => {
    window.localStorage.setItem(LS_TEXTURE, textureMode);
    if (textureMode === "color") {
      setActiveTextureUrl(COLOR_TEXTURE);
      return;
    }
    if (monoDataUrlRef.current) {
      setActiveTextureUrl(monoDataUrlRef.current);
      return;
    }
    makeMonoDataUrl(COLOR_TEXTURE, (dataUrl) => {
      monoDataUrlRef.current = dataUrl;
      setActiveTextureUrl(dataUrl);
    });
  }, [textureMode]);

  const resetView = useCallback(() => {
    ref.current?.pointOfView({ lat: 20, lng: 0, altitude: 2.4 }, 900);
  }, []);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <GlobeGL
        ref={ref}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl={activeTextureUrl}
        bumpImageUrl={BUMP_TEXTURE}
        showAtmosphere={true}
        atmosphereColor={colors.olive}
        atmosphereAltitude={textureMode === "color" ? 0.15 : 0.12}
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
      <GlobeControlChips
        textureMode={textureMode}
        autoRotate={autoRotate}
        onToggleTexture={() =>
          setTextureMode((m) => (m === "color" ? "mono" : "color"))
        }
        onToggleAutoRotate={() => setAutoRotate((v) => !v)}
        onResetView={resetView}
      />
    </div>
  );
}
