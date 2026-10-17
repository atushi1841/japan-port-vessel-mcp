# Japan Port Vessel Traffic MCP

OpenWaters AIS ベースの日本港湾船舶交通データ MCP サーバー。
API キー不要・完全無料・公開 AIS データ（tosa compliant）。

## Features

- **20 major Japanese ports** pre-configured with bounding boxes
- Real-time vessel position, name, IMO, flag, destination, ETA
- Historical track (up to 366 days)
- ETA & delay estimation (AIS-reported vs speed-projected)
- Port overview aggregation (counts by type, flag, status)

## Data source

Open Waters AIS — aggregate of community AIS receivers, AISHub, aisstream.
No official API key required for the anonymous tier.
Source: https://ais.openwaters.io/api/ais/

## Installation

```bash
git clone https://github.com/atushi1841/japan-port-vessel-mcp.git
cd japan-port-vessel-mcp
uv sync  # or: pip install -r requirements.txt
```

## Usage (stdio)

```bash
uv run --directory . src/stdio_main.py
```

Or configure in Claude Desktop / Cursor MCP settings:

```json
{
  "mcpServers": {
    "japan-port-vessel": {
      "command": "uv",
      "args": ["run", "--directory", "<path-to-repo>", "src/stdio_main.py"]
    }
  }
}
```

## Tools

| Tool | Description |
|---|---|
| `list_japan_ports()` | Catalog of 20 Japanese ports with bboxes |
| `get_vessels_in_port(port_code, limit=30)` | Live vessel list within a port bbox |
| `get_vessel(mmsi)` | Single-vessel latest position + static info |
| `get_vessel_track(mmsi, hours=24, interval="5m", limit=500)` | Historical track as GeoJSON coordinates |
| `estimate_vessel_eta(mmsi, port_code=None)` | ETA delay estimation |
| `get_port_overview(port_code, max_age_hours=6)` | Aggregated port activity summary |

## Quick examples

```python
# List Japanese ports
ports = list_japan_ports()

# Vessels in Tokyo Bay
tokyo = get_vessels_in_port("JPTYO", limit=20)

# ETA delay for a specific vessel
eta = estimate_vessel_eta("431005321", port_code="JPTYO")
print(eta["delay_hours"])
```

## License

MIT — like the Open Waters AIS network. Attribution required.

## Related

- Kensho project: https://github.com/atushi1841/kensho
- OpenWaters AIS API: https://ais.openwaters.io/api/ais/
