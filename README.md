# fp-tiler

Tile server for Field Papers. It serves Z/X/Y PNG tiles for snapshots (georeferenced images or scans of annotated paper maps). The GeoTIFFs are stored in S3 and the tiles are built from them on the fly. Deployed as an AWS Lambda function behind CloudFront.

## Endpoints

- `/health` - healthcheck
- `/snapshots/{id}/index.json` - TileJSON metadata
- `/snapshots/{id}/{z}/{x}/{y}.png` - 256x256 tiles
- `/snapshots/{id}/{z}/{x}/{y}@2x.png` - 512x512 tiles

## Environment Variables

- `PUBLIC_URL` - URL that the service is publicly available at (used in TileJSON URLs)
- `API_BASE_URL` - Field Papers API URL (default: `https://fieldpapers.org`)
- `GEOTIFF_CACHE_COUNT` - Max cached GeoTIFFs (default: `50`)
- `TILE_SIZE` - tile resolution in pixels, either `256` or `512` (default). both are available always; this setting just controls which one is advertised in the TileJSONs.

## Deployment

Deploy Lambda in the same region as the S3 bucket. Configure CloudFront to disable caching for `/health`.

## License

This code is available under the ISC license.
