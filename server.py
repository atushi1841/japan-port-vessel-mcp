#!/usr/bin/env python3
"""japan-port-vessel-mcp: Japanese port & vessel traffic MCP server.

Sources: Open Waters AIS (https://ais.openwaters.io) — free, no key, live
AIS positions for Japanese ports. Covers Tokyo, Yokohama, Nagoya, Kobe,
Osaka, Hakata, Nagasaki, Shimizu, Sendai, and more.

Tools
-----
- list_japan_ports          — catalog of 20 major ports with bounding boxes
- get_vessels_in_port       — live vessel snapshot in a port
- get_vessel                — single-vessel detail (name, IMO, flag, ETA, etc.)
- get_vessel_track          — historical track for a vessel
- estimate_vessel_eta       — ETA vs AIS-reported schedule; delay estimate
- get_port_overview         — port activity summary (counts by type/flag/status)

No API key required. Attribution via source=openwaters / aishub in each response.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

if __name__ not in sys.modules and "src" not in sys.modules:
    from fastmcp import FastMCP
else:
    from fastmcp import FastMCP

JST = timezone(timedelta(hours=9), "JST")

# ---------------------------------------------------------------------------
# Static data — Japanese major ports and their bounding boxes.
# bboxes are (lat_min, lon_min, lat_max, lon_max) centered on port basins.
# ---------------------------------------------------------------------------
JAPAN_PORTS: List[Dict[str, Any]] = [
    {"code": "JPYOK",  "name": "Yokohama / 横浜",          "lat": 35.33, "lon": 139.65, "bbox": [35.28, 139.58, 35.42, 139.72]},
    {"code": "JPTYO", "name": "Tokyo / 東京",              "lat": 35.66, "lon": 139.77, "bbox": [35.55, 139.70, 35.72, 139.95]},
    {"code": "JPKWJ", "name": "Kawasaki / 川崎",            "lat": 35.52, "lon": 139.70, "bbox": [35.45, 139.65, 35.58, 139.75]},
    {"code": "JPCYO", "name": "Chiba / 千葉",               "lat": 35.60, "lon": 140.12, "bbox": [35.52, 140.05, 35.68, 140.20]},
    {"code": "JPYSK", "name": "Yokosuka / 横須賀",          "lat": 35.19, "lon": 139.67, "bbox": [35.13, 139.63, 35.25, 139.72]},
    {"code": "JPSMZ", "name": "Shimizu / 清水",             "lat": 34.98, "lon": 138.49, "bbox": [34.92, 138.44, 35.04, 138.54]},
    {"code": "JPNMG", "name": "Nagoya / 名古屋",            "lat": 35.08, "lon": 136.90, "bbox": [35.02, 136.85, 35.14, 136.95]},
    {"code": "JPKBE", "name": "Kobe / 神戸",                "lat": 34.69, "lon": 135.18, "bbox": [34.63, 135.13, 34.75, 135.23]},
    {"code": "JPOSK", "name": "Osaka / 大阪",               "lat": 34.67, "lon": 135.50, "bbox": [34.58, 135.42, 34.72, 135.60]},
    {"code": "JPHKG", "name": "Himeji / 播磨",              "lat": 34.75, "lon": 134.75, "bbox": [34.70, 134.70, 34.80, 134.80]},
    {"code": "JPFUK", "name": "Hakata / 博多（福岡）",      "lat": 33.58, "lon": 130.40, "bbox": [33.52, 130.35, 33.64, 130.45]},
    {"code": "JPTKS", "name": "Kitakyushu / 北九州",        "lat": 33.88, "lon": 130.88, "bbox": [33.82, 130.82, 33.94, 130.94]},
    {"code": "JPNNG", "name": "Nagasaki / 長崎",            "lat": 32.75, "lon": 129.87, "bbox": [32.70, 129.83, 32.80, 129.91]},
    {"code": "JPSSB", "name": "Sasebo / 佐世保",            "lat": 33.14, "lon": 129.72, "bbox": [33.10, 129.68, 33.18, 129.76]},
    {"code": "JPSMJ", "name": "Shimonoseki / 下関",         "lat": 33.95, "lon": 130.93, "bbox": [33.90, 130.88, 34.00, 130.98]},
    {"code": "JPNIH", "name": "Niigata / 新潟",             "lat": 37.91, "lon": 139.05, "bbox": [37.86, 139.00, 37.96, 139.10]},
    {"code": "JPSDN", "name": "Sendai / 仙台",              "lat": 38.26, "lon": 141.03, "bbox": [38.20, 140.98, 38.32, 141.08]},
    {"code": "JPITU", "name": "Ishikari / 石狩",            "lat": 43.05, "lon": 141.33, "bbox": [43.00, 141.28, 43.10, 141.38]},
    {"code": "JPHMN", "name": "Hiroshima / 広島",           "lat": 34.37, "lon": 132.45, "bbox": [34.32, 34.42, 132.40, 132.50]},
    {"code": "JPNHA", "name": "Naha / 那覇（沖縄）",        "lat": 26.22, "lon": 127.68, "bbox": [26.17, 127.63, 26.27, 127.73]},
]

# AIS type -> human-readable label. Based on AIS type codes (IMO/CN).
AIS_TYPE_MAP: Dict[int, str] = {
    0: "Unknown", 10: "Wing-in-ground", 20: "Fishing", 30: "Tug", 31: "SAR",
    32: "Pilot vessel", 33: "AIS-SART", 34: "Recreational", 35: "Sailing",
    36: "HSC", 37: "Pilot", 38: "Military", 40: "Fishing", 45: "HSC",
    50: "Pilot", 51: "SAR", 52: "Recreational", 53: "HSC", 54: "Utility",
    55: "Recreational", 56: "Military", 60: "Passenger", 61: "Passenger HSC",
    62: "Utility", 63: "Passenger HSC", 70: "Cargo", 71: "Cargo HSC",
    72: "Utility", 73: "Cargo", 80: "Tanker", 81: "Tanker HSC",
    82: "Utility", 83: "Tanker", 90: "Other", 91: "Other HSC",
    92: "Utility", 93: "Other", 99: "Unknown",
}

NAV_STATUS: Dict[int, str] = {
    0: "Underway using engine", 1: "Moored", 2: "At anchor",
    3: "Restricted manoeuvrability", 4: "Constrained by draught",
    5: "Aground", 6: "Engaged in fishing", 7: "Underway sailing",
    8: "AIS-SART", 9: "Power-driven vessel towing astern",
    10: "Power-driven vessel pushing ahead", 11: "Reserved future use",
    14: "Not defined", 15: "Undefined",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
_API = "https://ais.openwaters.io/v1"

def _req(path: str, params: Optional[Dict[str, str]] = None, retries: int = 3) -> dict:
    url = f"{_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last_err: Optional[Exception] = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "japan-port-vessel-mcp/0.1 (OpenWaters)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8"))
        except Exception as e:
            last_err = e
            if i < retries - 1:
                import time; time.sleep(0.8 * (i + 1))
    raise RuntimeError(f"OpenWaters API error: {path} — {last_err}")


def _features_to_dict(fc: dict) -> dict:
    """Normalize GeoJSON FeatureCollection to a flat list for MCP output."""
    out: List[Dict[str, Any]] = []
    for feat in fc.get("features", []):
        p = feat.get("properties", {})
        g = feat.get("geometry", {})
        out.append({
            **p,
            "type_name": AIS_TYPE_MAP.get(p.get("type"), f"Type-{p.get('type')}"),
            "nav_status_name": NAV_STATUS.get(p.get("nav_status"), "Unknown"),
            "lat": g.get("coordinates", [None, None])[1] if g.get("coordinates") else None,
            "lon": g.get("coordinates", [None, None])[0] if g.get("coordinates") else None,
        })
    return out


# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="japan-port-vessel-mcp",
    instructions="""Japan Port Vessel Traffic Data MCP. Free AIS source (OpenWaters).
Use when you need Japanese port ship counts, vessel locations, ETA tracking, or delay estimates.
Tools: list_japan_ports, get_vessels_in_port, get_vessel, get_vessel_track, estimate_vessel_eta, get_port_overview.""",
)


@mcp.tool()
def list_japan_ports() -> dict:
    """Return a catalog of major Japanese ports with bounding boxes for AIS queries."""
    return {
        "count": len(JAPAN_PORTS),
        "ports": [
            {
                "code": p["code"],
                "name": p["name"],
                "lat": p["lat"],
                "lon": p["lon"],
                "bbox": p["bbox"],
                "bbox_description": (
                    f"lat {p['bbox'][0]}..{p['bbox'][2]}, "
                    f"lon {p['bbox'][1]}..{p['bbox'][3]}"
                ),
            }
            for p in JAPAN_PORTS
        ],
    }


@mcp.tool()
def get_vessels_in_port(port_code: str = "JPYOK", limit: int = 30) -> dict:
    """Return vessels currently within the named Japanese port bounding box.

    Args:
        port_code: ISO-like port code. Call list_japan_ports for valid codes.
        limit: max vessels returned (anonymous tier cap 500).
    """
    port = next((p for p in JAPAN_PORTS if p["code"] == port_code), None)
    if not port:
        return {"error": f"Unknown port code: {port_code}. Call list_japan_ports for valid codes."}
    bbox = port["bbox"]
    fc = _req("/vessels", params={
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "limit": str(limit),
        "max_age": "24h",
    })
    vessels = _features_to_dict(fc)
    # Classify into 'moving' vs 'stationary'
    moving: List[Dict[str, Any]] = []
    stationary: List[Dict[str, Any]] = []
    for v in vessels:
        sog = float(v.get("sog") or 0)
        ns = int(v.get("nav_status") or 0)
        if ns in (1, 2, 5) or sog < 1.0:
            stationary.append(v)
        else:
            moving.append(v)
    return {
        "port_code": port_code,
        "port_name": port["name"],
        "bbox": bbox,
        "total_vessels": len(vessels),
        "moving": moving,
        "stationary": stationary,
        "moving_count": len(moving),
        "stationary_count": len(stationary),
        "source": "Open Waters AIS (ais.openwaters.io)",
    }


@mcp.tool()
def get_vessel(mmsi: str) -> dict:
    """Fetch the latest known position and static information for a vessel by MMSI.

    Args:
        mmsi: nine-digit Maritime Mobile Service Identity. Leading zeros preserved.
    """
    r = _req(f"/vessels/{mmsi}")
    p = r.get("properties", {})
    g = r.get("geometry", {})
    return {
        "mmsi": p.get("mmsi"),
        "imo": p.get("imo"),
        "name": p.get("name"),
        "callsign": p.get("callsign"),
        "flag": p.get("flag"),
        "type": AIS_TYPE_MAP.get(p.get("type"), f"Type-{p.get('type')}"),
        "type_numeric": p.get("type"),
        "length_m": p.get("length"),
        "beam_m": p.get("beam"),
        "draught_m": p.get("draught"),
        "destination": p.get("destination"),
        "eta_aud": p.get("eta"),
        "lat": g.get("coordinates", [None, None])[1] if g.get("coordinates") else None,
        "lon": g.get("coordinates", [None, None])[0] if g.get("coordinates") else None,
        "sog_kn": float(p.get("sog") or 0),
        "cog_deg": float(p.get("cog") or 0),
        "heading_deg": float(p.get("heading") or 0),
        "nav_status": p.get("nav_status"),
        "nav_status_name": NAV_STATUS.get(int(p.get("nav_status") or 0), "Unknown"),
        "near": p.get("near"),
        "first_seen": p.get("first_seen"),
        "last_seen": p.get("seen"),
        "source": p.get("source"),
        "station": p.get("station"),
    }


@mcp.tool()
def get_vessel_track(mmsi: str, hours: int = 24, interval: str = "5m", limit: int = 500) -> dict:
    """Return the past trajectory of a vessel as GeoJSON-style positions.

    Args:
        mmsi: vessel MMSI.
        hours: how far back (defaults to 24h, up to 366d).
        interval: granularity — e.g. '5m', '15m', '1h'.
        limit: max points (anon cap 1000).
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    from_str = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = _req(f"/vessels/{mmsi}/track", params={
        "from": from_str,
        "to": now_str,
        "interval": interval,
        "limit": str(limit),
        "format": "geojson",
    })
    props = r.get("properties", {})
    geom = r.get("geometry", {})
    points = geom.get("coordinates", [])
    return {
        "mmsi": props.get("mmsi"),
        "name": props.get("name"),
        "from": props.get("from"),
        "to": props.get("to"),
        "points_returned": len(points),
        "points": points,
        "simplified": geom.get("simplified"),
        "truncated": geom.get("truncated"),
        "source": props.get("source"),
    }


@mcp.tool()
def estimate_vessel_eta(mmsi: str, port_code: Optional[str] = None) -> dict:
    """Estimate a vessel's arrival at its reported destination port.

    Compares the AIS-reported ETA (`eta` field) against a speed-based projection
    to infer delay. Also shows distance and travel-time estimates.

    Args:
        mmsi: vessel MMSI.
        port_code: optional explicit port code to validate destination against.
    """
    r = _req(f"/vessels/{mmsi}")
    p = r.get("properties", {})
    g = r.get("geometry", {})
    lat = g.get("coordinates", [None, None])[1]
    lon = g.get("coordinates", [None, None])[0]
    sog = float(p.get("sog") or 0)
    nav_status = int(p.get("nav_status") or 0)
    eta_aud = p.get("eta")  # string like "10-17 08:15"
    dest = p.get("destination")

    # Determine port if not given — parse >JP KWS DU NISSIN style
    given_port = port_code
    reported_port: Optional[str] = None
    if dest:
        # Extract first JP-code token after >JP
        import re
        m = re.search(r">\s*JP\s*([A-Z0-9]+)", dest, re.IGNORECASE)
        if m:
            reported_port = m.group(1).upper()

    use_port = given_port or reported_port

    # Distance to port
    dist_nm: Optional[float] = None
    if use_port:
        port = next((x for x in JAPAN_PORTS if x["code"] == use_port), None)
        if port and lat is not None and lon is not None:
            import math
            lat1, lon1 = math.radians(lat), math.radians(lon)
            lat2, lon2 = math.radians(port["lat"]), math.radians(port["lon"])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            dist_nm = round(1.852 * 60 * c, 2)
        else:
            use_port = None

    # ETA parsing
    now_jst = datetime.now(JST)
    projected_eta: Optional[datetime] = None
    if dist_nm is not None and sog > 0.5:
        projected_eta = now_jst + timedelta(hours=dist_nm / (sog * 1.852))

    parsed_eta: Optional[datetime] = None
    if eta_aud:
        try:
            # Format: "MM-DD HH:MM" (year inferred from now)
            parts = eta_aud.strip().split(" ")
            mmdd, hm = parts[0], parts[1]
            y = now_jst.year
            # handle leap-year-ish dates ok
            parsed_eta = datetime.strptime(f"{y}-{mmdd} {hm}", "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        except Exception:
            pass

    delay_hours: Optional[float] = None
    if projected_eta and parsed_eta:
        diff = (parsed_eta - projected_eta).total_seconds() / 3600
        delay_hours = round(diff, 2)

    return {
        "mmsi": p.get("mmsi"),
        "name": p.get("name"),
        "imo": p.get("imo"),
        "current_position": {"lat": lat, "lon": lon},
        "sog_kn": sog,
        "nav_status": p.get("nav_status"),
        "nav_status_name": NAV_STATUS.get(nav_status, "Unknown"),
        "reported_destination": dest,
        "estimated_destination_port": use_port,
        "distance_to_port_nm": dist_nm,
        "ais_reported_eta": eta_aud,
        "ais_parsed_eta_utc": parsed_eta.strftime("%Y-%m-%dT%H:%M:%SZ") if parsed_eta else None,
        "speed_projected_eta": projected_eta.strftime("%Y-%m-%dT%H:%M:%SZ") if projected_eta else None,
        "delay_hours": delay_hours,
        "status": (
            "at_port" if nav_status in (1, 2, 5)
            else ("delayed" if delay_hours and delay_hours > 1
                  else ("on_time" if delay_hours is not None else "calc_failed"))
        ),
        "notes": "Delay sign convention: positive = later than AIS-reported ETA (delayed), negative = early.",
    }


@mcp.tool()
def get_port_overview(port_code: str = "JPYOK", max_age_hours: int = 6) -> dict:
    """Aggregated overview of a Japanese port's vessel traffic.

    Returns counts by vessel type, flag, and navigation status.
    """
    port = next((p for p in JAPAN_PORTS if p["code"] == port_code), None)
    if not port:
        return {"error": f"Unknown port code: {port_code}. Call list_japan_ports for valid codes."}
    fc = _req("/vessels", params={
        "bbox": f"{port['bbox'][0]},{port['bbox'][1]},{port['bbox'][2]},{port['bbox'][3]}",
        "max_age": f"{max_age_hours}h",
        "limit": "500",
    })
    vessels = _features_to_dict(fc)

    by_type: Dict[str, int] = {}
    by_flag: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    moving_total = 0
    stationary_total = 0
    for v in vessels:
        t = v.get("type_name", "Unknown")
        f = v.get("flag", "ZZ")
        ns = int(v.get("nav_status") or 0)
        by_type[t] = by_type.get(t, 0) + 1
        by_flag[f] = by_flag.get(f, 0) + 1
        if ns in (1, 2, 5) or float(v.get("sog") or 0) < 1.0:
            stationary_total += 1
        else:
            moving_total += 1
    by_status["moving"] = moving_total
    by_status["stationary"] = stationary_total

    top_vessels = sorted(vessels, key=lambda v: float(v.get("sog") or 0), reverse=True)[:5]
    return {
        "port_code": port_code,
        "port_name": port["name"],
        "bbox": port["bbox"],
        "max_age_hours": max_age_hours,
        "total_vessels": len(vessels),
        "by_type": by_type,
        "by_flag": by_flag,
        "by_status": by_status,
        "fastest_vessels": [
            {"name": v.get("name"), "mmsi": v.get("mmsi"), "sog_kn": v.get("sog"), "flag": v.get("flag")}
            for v in top_vessels
        ],
    }


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
