# Changelog

## v3.0.1 - 2026-10-27

* Bump fastapi and uv-build
* Bump GH Actions dependencies

## v3.0.0 - 2026-10-27

* Rewrite in Python using rio-tiler (the same engine used in TiTiler). GeoTIFFs
  are now read with HTTP range requests instead of being downloaded in full, and
  overviews are used when present (Cloud Optimized GeoTIFFs).
* Fix speckles in snapshot tiles where a pixel had the nodata value (153) in
  some but not all bands.
* Tiles are now resampled bilinearly instead of using nearest neighbor.
* TileJSON zoom ranges are now based on the snapshot's native resolution.
* Return 404 for unknown snapshots and bad tile coordinates instead of 500.

## v2.0.0 - 2025-11-19

* Rewrite the application as an AWS Lambda microservice. This avoids excessive
  S3 egress costs. We're deploying it behind CloudFront so it's also much
  faster now for repeat tile requests.

## v1.0.0 - 2025-02-07

* Upgrade to support Node 22
* Drop or replace outdated dependencies
* Replace snapshot previewer with MapLibre-based page

Note: v1.0.0 is a full rewrite of this project; see 0fd238f.

## v0.2.0 - 2016-04-22

* Add core server functionality (CORS, logging, Sentry, response timing, ...)
* Update `tilelive-raster` to pick up `tilelive-error` and `node-gdal` w/ JPEG
  and DEFLATE support
* Support path prefixing via `PATH_PREFIX`
* Update to `tilelive-raster@^0.3.0` to pick up `gdal` binaries on Node-5.x
* Relax Mapnik dependency to match `tilelive-mapnik` and `mapnik-omnivore`

## v0.1.0 - 2015-05-01

* Initial release
