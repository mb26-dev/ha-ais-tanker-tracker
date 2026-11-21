# Changelog

## 1.2.3 - 2026-11-21

- New project artwork: new icon and logo for Home Assistant and the Marketplace (`brand/`, including `@2x` versions),
  new README banner and GitHub social preview. The images are built from `images/artwork.jpg` by
  `.github/workflows/build-brand.yml`.

## 1.2.2 - 2026-11-20

- **Much smaller recorder database.** Device trackers no longer write a new state for every AIS message. A tracker now
  writes when it appears or disappears, when position, name, load state, nav status, destination, draught or source
  changed (at most every 5 minutes), and otherwise as a heartbeat every 30 minutes.
- Fast-changing tracker attributes (`speed_knots`, `course`, `heading`, `distance_km`, `bearing_deg`, `last_seen`) stay
  live in Home Assistant but are excluded from the recorder.
- The `vessels` list of the overview sensor was already excluded from the recorder; the live card is not affected.

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
