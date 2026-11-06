import os
import re
import time
from functools import cache

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from mangum import Mangum
from rasterio.errors import RasterioIOError
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import Reader
from rio_tiler.models import ImageData

# GDAL tuning for reading GeoTIFFs over HTTP with range requests. These must be
# set before GDAL opens anything, and apply to local development too.
for key, value in {
    'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR',
    'GDAL_INGESTED_BYTES_AT_OPEN': '32768',
    'GDAL_HTTP_MERGE_CONSECUTIVE_RANGES': 'YES',
    'GDAL_HTTP_MULTIPLEX': 'YES',
    'GDAL_HTTP_VERSION': '2',
    'CPL_VSIL_CURL_ALLOWED_EXTENSIONS': '.tif,.tiff',
    'CPL_VSIL_CURL_CACHE_SIZE': str(64 * 1024 * 1024),
    'GDAL_CACHEMAX': '64',
}.items():
    os.environ.setdefault(key, value)

S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'files.fieldpapers.org')
PUBLIC_URL = os.environ.get('PUBLIC_URL')
TILE_SIZE = int(os.environ.get('TILE_SIZE', '512'))
MAX_ZOOM = 24

# Make sure integer tile coordinates are given in their canonical form (no
# leading zeroes) so that each tile has one possible Cloudfront cache key.
# Eight digits is enough for MAX_ZOOM = 24.
COORD = r'0|[1-9]\d{0,7}'
TILE_COORD = re.compile(COORD)

# Some clients request e.g. `123@2x@2x.png`, which is treated like `123@2x.png`.
TILE_FILENAME = re.compile(rf'({COORD})((?:@2x)*)\.png')

# Field Papers snapshot slugs
SNAPSHOT_ID = re.compile(r'[a-z0-9]{8}')

# S3 responds 403 rather than 404 to anonymous requests for missing objects
MISSING = re.compile(r'HTTP response code: 40[34]\b')

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    ms = round((time.monotonic() - start) * 1000)
    print(f'{response.status_code} {request.method} {request.url.path} {ms}ms', flush=True)
    return response


@app.middleware('http')
async def allow_cors(request: Request, call_next):
    response = await call_next(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


def geotiff_url(snapshot_id: str) -> str:
    """URL of a snapshot's GeoTIFF (a COG), which fp-tasks writes to a fixed key."""
    return f'https://s3.amazonaws.com/{S3_BUCKET_NAME}/snapshots/{snapshot_id}/field-paper-{snapshot_id}.tiff'


def open_snapshot(snapshot_id: str) -> Reader:
    """Open a snapshot's GeoTIFF, raising a 404 if there isn't one."""
    if not SNAPSHOT_ID.fullmatch(snapshot_id):
        raise HTTPException(404, f'Snapshot {snapshot_id} not found')
    try:
        return Reader(geotiff_url(snapshot_id))
    except RasterioIOError as e:
        if MISSING.search(str(e)):
            raise HTTPException(404, f'Snapshot {snapshot_id} not found') from None
        raise


@cache
def blank_tile(size: int) -> bytes:
    data = np.ma.masked_all((3, size, size), dtype='uint8')
    return ImageData(data).render(img_format='PNG')


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/snapshots/{snapshot_id}/index.json')
def tilejson(snapshot_id: str, request: Request):
    with open_snapshot(snapshot_id) as src:
        west, south, east, north = src.get_geographic_bounds(src.tms.rasterio_geographic_crs)
        minzoom, maxzoom = src.minzoom, src.maxzoom

    base_url = PUBLIC_URL or str(request.base_url).rstrip('/')
    suffix = '@2x.png' if TILE_SIZE == 512 else '.png'
    return {
        'tilejson': '2.0.0',
        'name': f'fp-snapshot-{snapshot_id}',
        'format': 'png',
        'tileSize': TILE_SIZE,
        'tiles': [f'{base_url}/snapshots/{snapshot_id}/{{z}}/{{x}}/{{y}}{suffix}'],
        'minzoom': minzoom,
        'maxzoom': maxzoom,
        'bounds': [west, south, east, north],
        'center': [(west + east) / 2, (south + north) / 2, min(minzoom + 2, maxzoom)],
    }


@app.get('/snapshots/{snapshot_id}/{z}/{x}/{filename}')
def tile(snapshot_id: str, z: str, x: str, filename: str):
    m = TILE_FILENAME.fullmatch(filename)
    if not (m and TILE_COORD.fullmatch(z) and TILE_COORD.fullmatch(x)):
        raise HTTPException(404, f'Invalid tile {z}/{x}/{filename}')

    z, x, y = int(z), int(x), int(m[1])
    size = 512 if m[2] else 256
    
    if not (0 <= z <= MAX_ZOOM and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(404, f'Invalid tile {z}/{x}/{y}')

    try:
        with open_snapshot(snapshot_id) as src:
            # Below minzoom the whole snapshot fits in about one tile; there's
            # not much point in rasterizing tiles too far below this zooom
            if z < src.minzoom - 1:
                raise TileOutsideBounds(f'zoom {z} is below minzoom {src.minzoom}')

            img = src.tile(
                x,
                y,
                z,
                tilesize=size,
                indexes=(1, 2, 3),
                resampling_method='bilinear',
                reproject_method='bilinear',
            )
        png = img.render(img_format='PNG')
    except TileOutsideBounds:
        png = blank_tile(size)

    return Response(
        png,
        media_type='image/png',
        headers={'Cache-Control': 'public, max-age=31536000, immutable'},
    )


handler = Mangum(app)
