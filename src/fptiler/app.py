import json
import os
import re
import time
import warnings
from functools import cache, lru_cache
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from mangum import Mangum
from rio_tiler.errors import NoOverviewWarning, TileOutsideBounds
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

# Snapshots created before the switch to COGs have no overviews; that's expected.
warnings.filterwarnings('ignore', category=NoOverviewWarning)

API_BASE_URL = os.environ.get('API_BASE_URL', 'https://fieldpapers.org')
PUBLIC_URL = os.environ.get('PUBLIC_URL')
TILE_SIZE = int(os.environ.get('TILE_SIZE', 512))
MAX_ZOOM = 24

# Some clients request e.g. `123@2x@2x.png`, which is treated like `123@2x.png`.
TILE_FILENAME = re.compile(r'(\d+)((?:@2x)*)\.png')

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


@lru_cache(maxsize=1024)
def geotiff_url(snapshot_id: str) -> str:
    """Look up the URL of a snapshot's GeoTIFF via the Field Papers API."""
    try:
        with urlopen(f'{API_BASE_URL}/snapshots/{snapshot_id}.json', timeout=10) as res:
            data = json.load(res)
    except HTTPError as e:
        if e.code == 404:
            raise HTTPException(404, f'Snapshot {snapshot_id} not found')
        raise

    if not data.get('geotiff'):
        raise HTTPException(404, f'Snapshot {snapshot_id} has no GeoTIFF')
    return data['geotiff']['url']


@cache
def blank_tile(size: int) -> bytes:
    data = np.ma.masked_all((3, size, size), dtype='uint8')
    return ImageData(data).render(img_format='PNG')


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/snapshots/{snapshot_id}/index.json')
def tilejson(snapshot_id: str, request: Request):
    with Reader(geotiff_url(snapshot_id)) as src:
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
def tile(snapshot_id: str, z: int, x: int, filename: str):
    m = TILE_FILENAME.fullmatch(filename)
    if not m:
        raise HTTPException(404, f'Invalid tile filename {filename}')
    y = int(m[1])
    size = 512 if m[2] else 256
    if not (0 <= z <= MAX_ZOOM and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(404, f'Invalid tile {z}/{x}/{y}')

    try:
        with Reader(geotiff_url(snapshot_id)) as src:
            img = src.tile(
                x,
                y,
                z,
                tilesize=size,
                indexes=(1, 2, 3),
                resampling_method='bilinear',
                reproject_method='bilinear',
                # Legacy snapshots use rgb(153, 153, 153) as NODATA; this option
                # tells GDAL not to interpret each band's nodata value separately,
                # which would cause e.g. rgb(153, 154, 155) to be interpreted wrong
                vrt_options={'UNIFIED_SRC_NODATA': 'YES'},
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
