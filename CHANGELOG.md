# Changelog

## 1.2.1 - 2026-11-17

- Leaflet 1.9.4 (JS, CSS, images, BSD-2-Clause license) is now bundled under `custom_components/ais_tanker/www/leaflet/`
  and served from the integration's own static path. The card no longer loads anything from a CDN and works without internet access
  (map tiles excepted). The files are copied unmodified from the npm package by `.github/workflows/vendor-leaflet.yml`.
- HACS validation runs without ignored checks.

## 1.2.0 - 2026-11-14

First public release.

- Local SDR (AIS-catcher via MQTT), aisstream.io and AISHub sources, merged by MMSI
- Tanker filter (AIS ship types 80-89), size class and laden / ballast estimate
- Overview sensor, local / global counters, device trackers for the nearest tankers
- Persistent ship database: tankers are recognised immediately after a restart or reload
- MQTT is optional: without the MQTT integration the local source is skipped instead of blocking setup
- Bundled `tanker-radar-card` (v1.1.0), registered automatically by the integration
- Card: privacy mode (no home marker, rings, distance or bearing) for sharing screenshots
- Local brand images (icon and logo, light and dark)
