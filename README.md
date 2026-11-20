<p align="center">
  <img alt="AIS Tanker Tracker" src="custom_components/ais_tanker/brand/icon.png" width="140">
</p>

<h1 align="center">AIS Tanker Tracker</h1>

<p align="center">
  <b>Live tanker tracking for Home Assistant</b><br>
  Oil, chemical and gas tankers from your own AIS receiver and free online AIS feeds, shown on a nautical radar card.
</p>

<p align="center">
  <a href="https://github.com/mb26-dev/ha-ais-tanker-tracker/releases"><img src="https://img.shields.io/github/v/release/mb26-dev/ha-ais-tanker-tracker?style=flat-square" alt="Release"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5?style=flat-square&logo=home-assistant&logoColor=white" alt="Home Assistant">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=mb26-dev&repository=ha-ais-tanker-tracker&category=integration"><img src="https://img.shields.io/badge/HACS-Default-41BDF5?style=flat-square" alt="HACS Default"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/mb26-dev/ha-ais-tanker-tracker?style=flat-square" alt="License"></a>
  <a href="https://ko-fi.com/mb26dev"><img src="https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=flat-square&logo=ko-fi&logoColor=white" alt="Buy me a coffee on Ko-fi"></a>
</p>

![Tanker radar on satellite imagery](images/radar-satellite.jpg)

## What it does

AIS Tanker Tracker filters the AIS traffic around you (or around any sea area you choose) down to **tankers only**
(AIS ship types 80-89) and turns them into Home Assistant entities plus a full-screen radar card.

- **Three data sources, merged by MMSI**
  - **Local SDR**: your own receiver with [AIS-catcher](https://github.com/jvde-github/AIS-catcher) + RTL-SDR via MQTT (real time, no internet needed)
  - **[aisstream.io](https://aisstream.io)**: free real time websocket feed (API key, no hardware)
  - **[AISHub](https://www.aishub.net)**: data exchange for station owners who share their own feed
  - Priority when several sources report the same ship: local SDR > aisstream.io > AISHub
- **Tanker classification**: AIS tanker category (general / hazardous cat A-D), size class by length (Coastal/Bunker, Handysize/MR, Panamax/Aframax, Suezmax, VLCC/ULCC)
- **Laden / Ballast estimate** from reported draught vs. ship length
- **Entities**: one overview sensor with all vessels as attributes, counters for local and global sources, and a `device_tracker` for the nearest N tankers (so they appear on the standard HA map and in automations)
- **Persistent ship database**: ship type, name and dimensions are cached on disk, so tankers are recognised immediately after a restart instead of waiting for the next static AIS message (sent only every 6 minutes)
- **Bundled Lovelace card** `custom:tanker-radar-card`, loaded automatically, no extra resource needed
- **100% UI configuration**: config flow + options flow, no YAML

## Screenshots

| Vessel inspector | Dark tactical layer |
|---|---|
| ![Inspector](images/vessel-inspector.jpg) | ![Dark layer](images/radar-dark.jpg) |

| Bathymetry overview | Mobile |
|---|---|
| ![Bathymetry](images/radar-bathymetry.jpg) | <img src="images/mobile.jpg" width="260" alt="Mobile"> |

The card shows:

- Rotating SVG tanker markers coloured by load state, with wake for moving ships
- HUD with live status of every feed (RF / AISSTREAM / AISHUB) and counters (total, local, global, laden, ballast)
- Quick jumps: Home, Andaman & Malacca, Singapore Strait, Strait of Hormuz, Suez Canal, Fit All
- Filters: All / Laden only / Local RF only
- Three chart layers: Esri satellite, Esri ocean bathymetry, dark tactical, each with OpenSeaMap seamarks
- Range rings around home (10 / 25 / 50 km)
- Vessel inspector: hull profile with draught gauge, compass with COG / HDG, speed, dimensions, destination, ETA, size class, distance and bearing from home
- Nearest-tankers strip at the bottom
- Visual editor in the dashboard UI
- **Privacy mode** for screenshots: hides home marker, range rings, distance and bearing (all screenshots above were taken with it)

## Installation

### HACS / Home Assistant Marketplace (recommended)

AIS Tanker Tracker is part of the default HACS repository list, no custom repository needed.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mb26-dev&repository=ha-ais-tanker-tracker&category=integration)

1. Click the button above, or open HACS (**Settings > Marketplace** on Home Assistant 2026.11+) and search for **AIS Tanker Tracker**
2. Install it and restart Home Assistant

If you added this repository as a custom repository before, you can remove that entry; the installed integration and its settings stay as they are.

### Manual

1. Copy `custom_components/ais_tanker` into `/config/custom_components/`
2. Restart Home Assistant

Then: **Settings > Devices & services > Add integration > AIS Tanker Tracker**.

## Configuration

Everything is set in the UI. All fields can be changed later under **Configure**; the integration reloads by itself.

| Option | Description |
|---|---|
| Use local AIS-catcher via MQTT | Subscribe to AIS-catcher JSON messages. Needs the MQTT integration. If MQTT is not set up, this source is skipped with a warning. |
| MQTT topic | Default `ais/#` |
| aisstream.io API key | Free key from [aisstream.io](https://aisstream.io) (GitHub login). Empty = disabled |
| AISHub username / API key | Only for AISHub members (you need to share your own receiver). Empty = disabled |
| Zones | Sea areas for aisstream.io and AISHub. Empty = 3 degree box around your home location |
| AISHub request interval | Seconds between AISHub requests, minimum 65 (AISHub allows one request per minute) |
| Stale timeout | Ships without an update for this long are removed (default 30 min) |
| Maximum device trackers | Nearest N tankers that get a `device_tracker` (default 50, 0 = none) |
| Create demo tankers | Three simulated tankers in the Strait of Malacca, useful to try the card without any data source |

### Zones

Format: `name:latmin,latmax,lonmin,lonmax`, several zones separated by `;` or new lines.

```text
Singapore:0.9,1.6,103.3,104.6;Hormuz:24.5,27.5,54.5,58.5;Suez:27.5,31.5,32.0,34.0
```

More examples:

```text
Andaman_Malacca:1.0,9.5,97.0,104.5
Rotterdam:51.7,52.2,3.4,4.6
Gulf_of_Mexico:27.0,30.5,-97.5,-88.0
English_Channel:49.5,51.5,-2.0,2.0
```

### Important: online coverage

aisstream.io and AISHub get their data from **land-based volunteer receivers** only (about 40-70 km range each).
Satellite AIS is not included. Busy ports with many volunteers (Singapore, Rotterdam, many European and US coasts)
show lots of ships; remote areas, open ocean and some straits may show **nothing at all**, even though ships are there.
This is a limit of the free data, not of the integration. Your own receiver is the only way to guarantee coverage of your area.

## Your own receiver (recommended)

Hardware: RTL-SDR stick (for example RTL-SDR Blog V4) + a VHF marine antenna (162 MHz), as high as possible with a clear view to the sea.

1. Install the **AIS-catcher** Home Assistant app (add-on) and pass the USB stick through
2. Enable MQTT output with the **JSON_FULL** message format, topic for example `ais/data`, using the Home Assistant MQTT broker
3. Keep **Use local AIS-catcher via MQTT** enabled in the integration with topic `ais/#`

AIS-catcher equivalent settings:

```text
-Q mqtt://USER:PASSWORD@core-mosquitto:1883 TOPIC ais/data MSGFORMAT JSON_FULL
```

Tip: feed your station to AISHub as well. Station owners get an AISHub API key in return, which adds a second global source.

## Entities

| Entity | Content |
|---|---|
| `sensor.ais_tanker_overview` | Number of active tankers. Attributes: `vessels` (list with all data, up to 500), counters per source, feed status of MQTT / aisstream.io / AISHub |
| `sensor.ais_tanker_local_count` | Tankers received by the local SDR |
| `sensor.ais_tanker_global_count` | Tankers from aisstream.io + AISHub |
| `device_tracker.ais_tanker_<mmsi>` | Nearest N tankers with position, name, IMO, call sign, type, size class, speed, course, heading, draught, load state, dimensions, destination, ETA, distance and bearing from home, source, last seen |

Example automation trigger: a laden VLCC within 25 km.

```yaml
triggers:
  - trigger: template
    value_template: >
      {{ state_attr('sensor.ais_tanker_overview', 'vessels')
         | selectattr('vessel_class', 'search', 'VLCC')
         | selectattr('load_status', 'eq', 'Laden')
         | selectattr('distance_km', 'le', 25)
         | list | count > 0 }}
```

## Database size

The integration is built to keep the recorder small:

- The `vessels` list of the overview sensor and its message counters are excluded from the recorder.
- Device trackers write a new state at most every 5 minutes (plus a 30 minute heartbeat), and their fast-changing
  attributes (speed, course, heading, distance, bearing, last seen) are not recorded.

If you do not need tanker history at all, you can exclude the entities completely in `configuration.yaml`:

```yaml
recorder:
  exclude:
    entity_globs:
      - device_tracker.ais_tanker_*
      - sensor.ais_tanker_*
```

## Radar card

The card is shipped with the integration and registered automatically (`/ais_tanker_static/tanker-radar-card.js`).
Add it with the card picker (**AIS Tanker Radar Card**) or in YAML. Works best in a **Panel** view:

```yaml
type: custom:tanker-radar-card
entity: sensor.ais_tanker_overview
title: AIS Tanker Radar
map_height: calc(100vh - 110px)
default_layer: satellite
default_zoom: 9
show_range_rings: true
show_vessel_list: true
auto_fit: true
privacy_mode: false
```

| Option | Default | Description |
|---|---|---|
| `entity` | `sensor.ais_tanker_overview` | Overview sensor |
| `title` | `AIS Tanker Radar` | Title in the HUD |
| `map_height` | `620px` | Any CSS height, for example `80vh` |
| `default_layer` | `satellite` | `satellite`, `bathymetry` or `dark` |
| `default_zoom` | `9` | Start zoom |
| `center` | home | Optional start position `[lat, lon]` |
| `focus_mmsi` | - | Optional: open the inspector for this ship on load |
| `show_range_rings` | `true` | Range rings around home |
| `show_vessel_list` | `true` | Nearest-tankers strip |
| `auto_fit` | `true` | Zoom to all tankers if none is near home |
| `privacy_mode` | `false` | Hide home marker, range rings, distance and bearing |

If you used an earlier manual copy of the card, remove its dashboard resource to avoid loading it twice.

## Laden / ballast estimate

AIS does not transmit the cargo state. The integration compares the reported draught with the ship length
(draught / length ratio). Small tankers (< 120 m) use different thresholds than large ones. The result is an
estimate: crews do not always update the draught, so treat it as an indication, not a fact.

## Privacy and data

- The integration only contacts aisstream.io (subscription with your zones) and AISHub (zone requests).
- The card and the bundled Leaflet 1.9.4 library are served by the integration itself; no code is loaded from a CDN. Only the map tiles come from Esri and OpenSeaMap.
- Your API keys are stored in the Home Assistant config entry.
- The persistent ship cache lives in `.storage/ais_tanker.static_cache` (ship type, name, dimensions; entries expire after 14 days).

## Support

If the radar card keeps an eye on the tankers off your coast, a coffee keeps the project afloat. ☕🚢

<a href="https://ko-fi.com/mb26dev"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support me on Ko-fi"></a>

A star on GitHub, a bug report or a screenshot of your radar helps just as much. Thank you!

## Disclaimer

For hobby and information use only. **Not for navigation.** AIS data can be incomplete, delayed or wrong.
Map tiles: Esri (World Imagery, Ocean, Dark Gray Canvas) and OpenSeaMap; please respect their terms of use.
This project is not affiliated with aisstream.io, AISHub, Esri, OpenSeaMap or AIS-catcher.

## License

[MIT](LICENSE)
