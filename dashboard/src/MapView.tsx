import { useEffect, useRef } from "react";
import maplibregl, { Map as MLMap, Marker, Popup } from "maplibre-gl";
import type { Checkin, Resident, Resource } from "./api";
import { STATUS_META, statusOf } from "./status";

// Amazon Location Service map style when configured (VITE_MAP_STYLE), otherwise an open style.
const STYLE = (import.meta.env.VITE_MAP_STYLE as string | undefined) || "https://tiles.openfreemap.org/styles/fiord";

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
  const popups = useRef<Popup[]>([]);

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
    popups.current.forEach((p) => p.remove());
    popups.current = [];

    for (const c of resources) {
      if (!c.location || !["cooling_center", "warming_center"].includes(c.type)) continue;
      const warm = c.type === "warming_center";
      const d = document.createElement("div");
      d.className = "center-marker" + (warm ? " warm" : "") + (c.open_today === false ? " closed" : "");
      d.setAttribute("role", "button");
      d.setAttribute("tabindex", "0");
      d.setAttribute("aria-label", `${c.name}, ${c.address}`);
      const popup = new maplibregl.Popup({ offset: 12, closeButton: false, closeOnClick: false, maxWidth: "280px", className: "place-popup" })
        .setLngLat(c.location.coordinates).setHTML(placeHtml(c));
      let timer: ReturnType<typeof setTimeout> | undefined;
      const show = () => {
        clearTimeout(timer);
        if (popup.isOpen()) return;
        popups.current.forEach((p) => p !== popup && p.remove());
        popup.addTo(m);
        const el = popup.getElement();
        el.addEventListener("mouseenter", () => clearTimeout(timer));
        el.addEventListener("mouseleave", hide);
      };
      const hide = () => { clearTimeout(timer); timer = setTimeout(() => popup.remove(), 180); };
      d.addEventListener("mouseenter", show);
      d.addEventListener("mouseleave", hide);
      d.addEventListener("focus", show);
      d.addEventListener("blur", hide);
      d.addEventListener("click", (e) => { e.stopPropagation(); popup.isOpen() ? popup.remove() : show(); });
      popups.current.push(popup);
      markers.current.push(new maplibregl.Marker({ element: d }).setLngLat(c.location.coordinates).addTo(m));
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

const esc = (v: unknown) => String(v ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]!));

function placeHtml(c: Resource): string {
  const warm = c.type === "warming_center";
  const seed = !c.source_url || c.source_url === "seed";
  const checked = c.fetched_at ? new Date(c.fetched_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
  const status = c.open_today === false ? '<span class="pp-tag pp-closed">Closed today</span>'
    : c.open_today ? '<span class="pp-tag pp-open">Open today</span>' : "";
  let host = "";
  try { host = !seed && c.source_url ? new URL(c.source_url).hostname.replace(/^www\./, "") : ""; } catch { host = ""; }
  const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(c.address || c.name)}`;
  return `<div class="pp">
    <div class="pp-kind">${warm ? "Warming center" : "Cooling center"} ${status}</div>
    <div class="pp-name">${esc(c.name)}</div>
    <div class="pp-row">${esc(c.address)}</div>
    <div class="pp-row"><b>Today:</b> ${esc(c.hours_today || "hours unknown")}</div>
    ${c.notes ? `<div class="pp-row pp-notes">${esc(c.notes)}</div>` : ""}
    <div class="pp-src">${seed ? "Hours not verified today (seed data)" : `Hours checked ${esc(checked)}${host ? ` · ${esc(host)}` : ""}`}</div>
    <a class="pp-link" href="${maps}" target="_blank" rel="noopener noreferrer">Directions</a>
  </div>`;
}
