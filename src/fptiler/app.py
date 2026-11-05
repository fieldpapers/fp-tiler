import json
import os
import posixpath
import re
import time
import warnings
from functools import cache, lru_cache
from urllib.error import HTTPError
from urllib.parse import unquote, urlparse
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

# S3 endpoints in fp-tasks' (path-style) GeoTIFF URLs
S3_HOST = re.compile(r's3(\.[a-z0-9-]+)?\.amazonaws\.com')

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

    url = data['geotiff']['url']
    check_geotiff_url(url)
    return url


def check_geotiff_url(url: str):
    """
    Raise ValueError unless url is in S3_BUCKET_NAME. GDAL can open local files
    and many kinds of URLs, so this keeps a bad URL from the Field Papers API
    from reading anything else.
    """
    uri = urlparse(url)
    # resolve any ../ (including encoded ones) as an HTTP client would
    path = posixpath.normpath(unquote(uri.path))
    if not (
        uri.scheme in ('http', 'https')
        and S3_HOST.fullmatch(uri.hostname or '')
        and path.startswith(f'/{S3_BUCKET_NAME}/')
    ):
        raise ValueError(f'GeoTIFF URL {url} is not in the {S3_BUCKET_NAME} bucket')


def check_snapshot_id(snapshot_id: str):
    """404 for IDs that can't be snapshots, without asking the Field Papers API."""
    if not SNAPSHOT_ID.fullmatch(snapshot_id):
        raise HTTPException(404, f'Snapshot {snapshot_id} not found')


@cache
def blank_tile(size: int) -> bytes:
    data = np.ma.masked_all((3, size, size), dtype='uint8')
    return ImageData(data).render(img_format='PNG')


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/snapshots/{snapshot_id}/index.json')
def tilejson(snapshot_id: str, request: Request):
    check_snapshot_id(snapshot_id)
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
def tile(snapshot_id: str, z: str, x: str, filename: str):
    check_snapshot_id(snapshot_id)
    
    m = TILE_FILENAME.fullmatch(filename)
    if not (m and TILE_COORD.fullmatch(z) and TILE_COORD.fullmatch(x)):
        raise HTTPException(404, f'Invalid tile {z}/{x}/{filename}')
    
    z, x, y = int(z), int(x), int(m[1])
    size = 512 if m[2] else 256
    
    if not (0 <= z <= MAX_ZOOM and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(404, f'Invalid tile {z}/{x}/{y}')

    try:
        with Reader(geotiff_url(snapshot_id)) as src:
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
