import { useEffect, useRef } from "react";
import maplibregl, { Map as MLMap, Marker } from "maplibre-gl";
import type { Checkin, Resident, Resource } from "./api";
import { STATUS_META, statusOf } from "./status";

// Amazon Location Service map style when configured (VITE_MAP_STYLE), otherwise an open style.
const STYLE = (import.meta.env.VITE_MAP_STYLE as string | undefined) || "https://tiles.openfreemap.org/styles/positron";

interface Props {
  residents: Resident[];
  latest: Map<string, Checkin>;
  resources: Resource[];
  onSelect: (r: Resident) => void;
}

export default function MapView({ residents, latest, resources, onSelect }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const markers = useRef<Marker[]>([]);

  useEffect(() => {
    if (!el.current || map.current) return;
    map.current = new maplibregl.Map({
      container: el.current, style: STYLE, center: [-112.0, 33.45], zoom: 9.6, attributionControl: { compact: true },
    });
    map.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    return () => { map.current?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    markers.current.forEach((mk) => mk.remove());
    markers.current = [];

    for (const c of resources) {
      if (!c.location || c.type !== "cooling_center" || c.source_url === "seed") continue;
      const d = document.createElement("div");
      d.className = "center-marker";
      d.title = c.name;
      const popup = new maplibregl.Popup({ offset: 10 }).setHTML(
        `<div style="font:13px Inter,sans-serif"><b>${c.name}</b><br/>${c.hours_today || ""}<br/><span style="color:#78716c">${c.address}</span></div>`);
      markers.current.push(new maplibregl.Marker({ element: d }).setLngLat(c.location.coordinates).setPopup(popup).addTo(m));
    }

    for (const r of residents) {
      if (!r.location) continue;
      const st = statusOf(r, latest.get(r._id));
      const d = document.createElement("div");
      d.className = "marker" + (st === "emergency" || st === "calling" || st === "warning" ? " pulse" : "");
      d.style.background = STATUS_META[st].color;
      if (r.playbook === "crew") d.style.borderRadius = "4px";
      d.title = `${r.name}: ${STATUS_META[st].label}`;
      d.addEventListener("click", () => onSelect(r));
      markers.current.push(new maplibregl.Marker({ element: d }).setLngLat(r.location.coordinates).addTo(m));
    }
  }, [residents, latest, resources, onSelect]);

  return <div ref={el} className="h-full w-full" />;
}
