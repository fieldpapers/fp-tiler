# Changelog

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
