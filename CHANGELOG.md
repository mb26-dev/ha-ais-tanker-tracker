# Changelog

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
