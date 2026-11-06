# fp-tiler

Tile server for [Field Papers](https://fieldpapers.org). It serves Z/X/Y PNG tiles for snapshots (georeferenced scans or photos of annotated paper maps).

## Overview

Snapshots are stored in S3 as Cloud Optimized GeoTIFFs (COGs) with overviews and an internal mask for transparency. fp-tasks writes each snapshot's COG to `snapshots/{id}/field-paper-{id}.tiff`, so fp-tiler reads it from there directly and renders tiles on the fly using [rio-tiler](https://github.com/cogeotiff/rio-tiler). COGs are read with HTTP range requests, so only the parts needed for a tile are fetched, and low-zoom tiles are rendered from overviews. It runs as an AWS Lambda function, in the same region as the S3 bucket, behind CloudFront.

## Endpoints

- `/health` - healthcheck
- `/snapshots/{id}/index.json` - TileJSON metadata
- `/snapshots/{id}/{z}/{x}/{y}.png` - 256x256 tiles
- `/snapshots/{id}/{z}/{x}/{y}@2x.png` - 512x512 tiles

Tiles outside a snapshot's bounds are returned as fully transparent PNGs. Snapshots without a GeoTIFF in S3 return 404. The TileJSON zoom range is derived from the snapshot's native resolution, but tiles can be requested at any zoom from 0 to 24.

## Environment Variables

- `PUBLIC_URL` - URL that the service is publicly available at (used in TileJSON URLs); defaults to the request's origin
- `S3_BUCKET_NAME` - S3 bucket that snapshot GeoTIFFs are read from (default: `files.fieldpapers.org`)
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
