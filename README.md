# fp-tiler

Tile server for [Field Papers](https://fieldpapers.org). It serves Z/X/Y PNG tiles for snapshots (georeferenced scans or photos of annotated paper maps).

## Overview

Snapshots are stored as GeoTIFFs in S3. fp-tiler looks up a snapshot's GeoTIFF URL via the Field Papers API, then renders tiles on the fly using [rio-tiler](https://github.com/cogeotiff/rio-tiler). GeoTIFFs are read with HTTP range requests, so only the parts needed for a tile are fetched. It runs as an AWS Lambda function, in the same region as the S3 bucket, behind CloudFront.

Two flavors of GeoTIFF are supported:

- **Cloud Optimized GeoTIFFs** with overviews and an alpha band or internal mask for transparency. This is the preferred format, since low-zoom tiles can be rendered from overviews.
- **Legacy tiled GeoTIFFs** without overviews, using a nodata value of 153 in every band. A pixel is treated as transparent only if all of its bands are 153. These work, but low-zoom tiles are slower because the full-resolution image must be read.

## Endpoints

- `/health` - healthcheck
- `/snapshots/{id}/index.json` - TileJSON metadata
- `/snapshots/{id}/{z}/{x}/{y}.png` - 256x256 tiles
- `/snapshots/{id}/{z}/{x}/{y}@2x.png` - 512x512 tiles

Tiles outside a snapshot's bounds are returned as fully transparent PNGs. The TileJSON zoom range is derived from the snapshot's native resolution, but tiles can be requested at any zoom from 0 to 24.

## Environment Variables

- `PUBLIC_URL` - URL that the service is publicly available at (used in TileJSON URLs); defaults to the request's origin
- `API_BASE_URL` - Field Papers API URL (default: `https://fieldpapers.org`)
- `TILE_SIZE` - tile resolution advertised in TileJSON, either `256` or `512` (default). Both sizes are always available.

GDAL configuration options (e.g. `CPL_VSIL_CURL_CACHE_SIZE`) can also be set via the environment to override the defaults in `app.py`.

## Development

Requires [uv](https://docs.astral.sh/uv/). To run a local server:

```
uv run uvicorn fptiler.app:app --reload
```

Then visit e.g. `http://localhost:8000/snapshots/2gw5f7o9/index.json`. Snapshot GeoTIFFs are publicly readable, so no AWS credentials are needed.

To run the tests:

```
uv run pytest
```

## Deployment

The `Dockerfile` defines an image for the AWS Lambda Python runtime (`linux/amd64`), with `fptiler.app.handler` as the entrypoint. The Lambda should be deployed in the same region as the S3 bucket and be exposed via a Function URL. If CloudFront is used, caching should be disabled for the `/health` endpoint.

## License

This code is available under the ISC license; see the LICENSE file for details.
