import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import GlobeGL from "react-globe.gl";
import type { GlobeMethods } from "react-globe.gl";

import { colors, fonts, space } from "../styles/tokens";
import type { GlobeDot } from "../types";

interface Props {
  dots: GlobeDot[];
  onSelect: (slug: string) => void;
  selectedSlug: string | null;
}

interface PointDatum extends GlobeDot {
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
type ViewMode = "dots" | "hex";

const COLOR_TEXTURE = "//unpkg.com/three-globe/example/img/earth-blue-marble.jpg";
const BUMP_TEXTURE = "//unpkg.com/three-globe/example/img/earth-topology.png";

const LS_TEXTURE = "cc.globe.texture";
const LS_AUTOROTATE = "cc.globe.autoRotate";
const LS_BORDERS = "cc.globe.borders";
const LS_VIEWMODE = "cc.globe.viewMode";

function dotRadius(eventCount: number): number {
  return 0.22 + 0.09 * Math.log1p(eventCount);
}

function formatWeek(iso: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

function lerpHex(from: [number, number, number], to: [number, number, number], t: number): string {
  const r = Math.round(from[0] + (to[0] - from[0]) * t);
  const g = Math.round(from[1] + (to[1] - from[1]) * t);
  const b = Math.round(from[2] + (to[2] - from[2]) * t);
  return `rgb(${r},${g},${b})`;
}

// Olive → active red ramp for intensity
const OLIVE_RGB: [number, number, number] = [0x6b, 0x73, 0x54];
const ACTIVE_RGB: [number, number, number] = [0xa6, 0x4a, 0x3a];

function intensityColor(weight: number): string {
  const t = Math.min(1, Math.log1p(weight) / 8);
  return lerpHex(OLIVE_RGB, ACTIVE_RGB, t);
}

// Every dot is current by construction, so colour carries lethality rather
// than status: olive = activity without reported deaths, red = high fatalities.
export function lethalityColor(fatalities: number): string {
  return intensityColor(fatalities);
}

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
  showBorders,
  viewMode,
  onToggleTexture,
  onToggleAutoRotate,
  onToggleBorders,
  onToggleView,
  onResetView,
}: {
  textureMode: TextureMode;
  autoRotate: boolean;
  showBorders: boolean;
  viewMode: ViewMode;
  onToggleTexture: () => void;
  onToggleAutoRotate: () => void;
  onToggleBorders: () => void;
  onToggleView: () => void;
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
        onClick={onToggleView}
        style={{
          ...chipStyle,
          color: viewMode === "hex" ? colors.oliveLight : colors.textMuted,
        }}
        title="Toggle dot view vs hex intensity heatmap"
      >
        [ {viewMode === "hex" ? "HEX" : "DOTS"} ]
      </button>
      <button
        type="button"
        onClick={onToggleBorders}
        style={{
          ...chipStyle,
          color: showBorders ? colors.oliveLight : colors.textMuted,
        }}
        title="Toggle country borders and capitals"
      >
        [ BORDERS {showBorders ? "ON" : "OFF"} ]
      </button>
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

export function Globe({ dots, onSelect, selectedSlug }: Props) {
  const ref = useRef<GlobeMethods | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  const monoDataUrlRef = useRef<string | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  const [textureMode, setTextureMode] = useState<TextureMode>(() =>
    readLocal<TextureMode>(LS_TEXTURE, "color"),
  );
  const [autoRotate, setAutoRotate] = useState<boolean>(
    () => readLocal(LS_AUTOROTATE, "false") === "true",
  );
  const [showBorders, setShowBorders] = useState<boolean>(
    () => readLocal(LS_BORDERS, "true") === "true",
  );
  const [viewMode, setViewMode] = useState<ViewMode>(() =>
    readLocal<ViewMode>(LS_VIEWMODE, "dots"),
  );
  const [activeTextureUrl, setActiveTextureUrl] = useState<string>(COLOR_TEXTURE);
  const [countriesGeo, setCountriesGeo] = useState<object[]>([]);

  const points: PointDatum[] = useMemo(
    () =>
      dots.map((d) => ({ ...d, __color: lethalityColor(d.fatalities_4w) })),
    [dots],
  );

  const displayedCountries = useMemo<object[]>(
    () => (showBorders ? countriesGeo : []),
    [showBorders, countriesGeo],
  );

  // Regions significant enough to carry a standing label on the globe.
  const labelled: PointDatum[] = useMemo(() => {
    const ranked = [...points].sort(
      (a, b) =>
        b.fatalities_4w - a.fatalities_4w || b.events_4w - a.events_4w,
    );
    return ranked.slice(0, 45);
  }, [points]);

  // Pulse only the most lethal regions — every dot is current, so a ring on
  // each would be noise rather than signal.
  const rings: RingDatum[] = useMemo(() => {
    const threshold = 25;
    return dots
      .filter((d) => d.fatalities_4w >= threshold)
      .map((d) => ({
        lat: d.lat,
        lng: d.lng,
        maxRadius: 4,
        propagationSpeed: 2,
        repeatPeriod: 2000,
      }));
  }, [dots]);

  // Track container size so the globe canvas matches its parent (not the window).
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () =>
      setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Load country borders GeoJSON from bundled static file.
  useEffect(() => {
    fetch("/geo/countries.geojson")
      .then((r) => r.json())
      .then((d) => setCountriesGeo((d.features ?? []) as object[]))
      .catch(() => {});
  }, []);

  // Apply OrbitControls tuning once.
  useEffect(() => {
    const g = ref.current;
    if (!g) return;
    const c = g.controls() as Record<string, unknown>;
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
    const c = g.controls() as Record<string, unknown>;
    c.autoRotate = autoRotate;
    c.autoRotateSpeed = 0.25;
    window.localStorage.setItem(LS_AUTOROTATE, String(autoRotate));
  }, [autoRotate]);

  // Persist borders toggle.
  useEffect(() => {
    window.localStorage.setItem(LS_BORDERS, String(showBorders));
  }, [showBorders]);

  // Persist view mode.
  useEffect(() => {
    window.localStorage.setItem(LS_VIEWMODE, viewMode);
  }, [viewMode]);

  // Fly to selected conflict.
  useEffect(() => {
    const g = ref.current;
    if (!g || !selectedSlug) return;
    const target = dots.find((d) => d.slug === selectedSlug);
    if (!target) return;
    g.pointOfView({ lat: target.lat, lng: target.lng, altitude: 1.6 }, 900);
  }, [selectedSlug, dots]);

  // Switch texture by updating the globeImageUrl prop.
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
    <div ref={containerRef} style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      <GlobeGL
        ref={ref}
        width={size.w || undefined}
        height={size.h || undefined}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl={activeTextureUrl}
        bumpImageUrl={BUMP_TEXTURE}
        showAtmosphere={true}
        atmosphereColor={colors.olive}
        atmosphereAltitude={textureMode === "color" ? 0.15 : 0.12}
        // Country border polygons
        polygonsData={displayedCountries}
        polygonCapColor={() => "rgba(0,0,0,0)"}
        polygonSideColor={() => "rgba(0,0,0,0)"}
        polygonStrokeColor={() => colors.textMuted}
        polygonAltitude={0.005}
        polygonLabel={(d: object) => {
          const name = (d as { properties?: { NAME?: string } }).properties?.NAME ?? "";
          return name
            ? `<div style="
                font-family:${fonts.mono};
                background:${colors.bgSunken};
                color:${colors.textMuted};
                border:1px solid ${colors.rule};
                padding:3px 8px;
                font-size:10px;
                letter-spacing:0.14em;
              ">${name}</div>`
            : "";
        }}
        // Crisis dots (dots view)
        pointsData={viewMode === "dots" ? points : []}
        pointLat={(d) => (d as PointDatum).lat}
        pointLng={(d) => (d as PointDatum).lng}
        pointColor={(d) => (d as PointDatum).__color}
        pointAltitude={0.006}
        pointRadius={(d) => dotRadius((d as PointDatum).events_4w)}
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
            <div style="font-size:13px;">${p.name}</div>
            <div style="color:${colors.textMuted};font-size:10px;margin-top:3px;">${p.events_4w} events${p.fatalities_4w > 0 ? ` · † ${p.fatalities_4w}` : ""} · 4 wks to ${formatWeek(p.latest_week)}</div>
            ${
              p.conflict
                ? `<div style="color:${colors.oliveLight};font-size:10px;margin-top:3px;">part of ${p.conflict.name}</div>`
                : ""
            }
          </div>`;
        }}
        onPointClick={(p) => onSelect((p as PointDatum).slug)}
        // Standing labels for the most significant regions, so the globe is
        // readable without hovering every dot. Labelling all 350 would be a
        // wall of text, so only the top slice by activity gets one.
        labelsData={viewMode === "dots" ? labelled : []}
        labelLat={(d: object) => (d as PointDatum).lat}
        labelLng={(d: object) => (d as PointDatum).lng}
        labelText={(d: object) => (d as PointDatum).admin1 ?? (d as PointDatum).name}
        labelColor={() => colors.text}
        labelSize={0.42}
        labelDotRadius={0}
        labelResolution={2}
        labelAltitude={0.012}
        labelIncludeDot={false}
        onLabelClick={(d: object) => onSelect((d as PointDatum).slug)}
        ringsData={viewMode === "dots" ? rings : []}
        ringLat={(d) => (d as RingDatum).lat}
        ringLng={(d) => (d as RingDatum).lng}
        ringMaxRadius={(d) => (d as RingDatum).maxRadius}
        ringPropagationSpeed={(d) => (d as RingDatum).propagationSpeed}
        ringRepeatPeriod={(d) => (d as RingDatum).repeatPeriod}
        ringColor={() => colors.active}
        // Hex intensity view
        hexBinPointsData={viewMode === "hex" ? points : []}
        hexBinPointLat={(d: object) => (d as PointDatum).lat}
        hexBinPointLng={(d: object) => (d as PointDatum).lng}
        hexBinPointWeight={(d: object) => Math.max(1, (d as PointDatum).events_4w)}
        hexBinResolution={3}
        hexMargin={0.2}
        hexAltitude={(d: { sumWeight: number }) =>
          0.01 + 0.045 * Math.log1p(d.sumWeight)
        }
        hexTopColor={(d: { sumWeight: number }) => intensityColor(d.sumWeight)}
        hexSideColor={(d: { sumWeight: number }) => intensityColor(d.sumWeight)}
        hexLabel={(d: { points: PointDatum[]; sumWeight: number }) => {
          const total = Math.round(d.sumWeight);
          const n = d.points.length;
          const topNames = d.points
            .slice()
            .sort((a, b) => b.events_4w - a.events_4w)
            .slice(0, 3)
            .map((p) => p.name);
          return `<div style="
            font-family:'IBM Plex Mono',monospace;
            background:${colors.bgRaised};
            color:${colors.text};
            border:1px solid ${colors.ruleStrong};
            padding:6px 10px;
            font-size:11px;
          ">
            <div style="color:${colors.oliveLight};font-size:10px;letter-spacing:0.2em;">[ CLUSTER ]</div>
            <div style="margin-top:2px;">${n} REGION${n !== 1 ? "S" : ""} · ${total} EVENTS</div>
            <div style="color:${colors.textMuted};font-size:10px;margin-top:3px;">${topNames.join("<br/>")}</div>
          </div>`;
        }}
      />
      {viewMode === "hex" && (
        <div
          style={{
            position: "absolute",
            top: space.md,
            left: space.md,
            maxWidth: 340,
            background: colors.bgRaised,
            border: `1px solid ${colors.rule}`,
            borderLeft: `2px solid ${colors.active}`,
            padding: `${space.sm}px ${space.md}px`,
            fontFamily: fonts.mono,
            fontSize: 10,
            lineHeight: 1.5,
            color: colors.textMuted,
            letterSpacing: "0.04em",
            zIndex: 2,
          }}
        >
          <div
            className="stamp"
            style={{
              color: colors.active,
              fontSize: 10,
              letterSpacing: "0.22em",
              marginBottom: 4,
            }}
          >
            // DATA CAVEAT
          </div>
          Hex height + color reflect total <strong style={{ color: colors.text }}>event count</strong>, not
          lethality or severity. A region with many small protests will appear
          taller than one with fewer high-fatality incidents. For true
          intensity, cross-reference fatality (†) counts in individual dossiers.
        </div>
      )}

      <GlobeControlChips
        textureMode={textureMode}
        autoRotate={autoRotate}
        showBorders={showBorders}
        viewMode={viewMode}
        onToggleTexture={() =>
          setTextureMode((m) => (m === "color" ? "mono" : "color"))
        }
        onToggleAutoRotate={() => setAutoRotate((v) => !v)}
        onToggleBorders={() => setShowBorders((v) => !v)}
        onToggleView={() => setViewMode((v) => (v === "dots" ? "hex" : "dots"))}
        onResetView={resetView}
      />
    </div>
  );
}
