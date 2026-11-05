import io
import json

import morecantile
import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from PIL import Image
from rasterio.shutil import copy as rio_copy
from rasterio.transform import from_bounds

from fptiler import app as fp

TILE = morecantile.Tile(x=10498, y=22872, z=16)
SIZE = 512


def write_snapshot(path, compress=None):
    """
    Write a 3857 GeoTIFF covering exactly TILE at SIZE px. The left half is
    nodata, the right half is valid with a column of pixels whose green band
    happens to equal 153.

    With no compression, this is the legacy format (nodata=153, no overviews).
    Otherwise it's a COG with an alpha band (or mask, for JPEG).
    """
    rgb = np.full((3, SIZE, SIZE), 153, dtype='uint8')
    rgb[:, :, SIZE // 2 :] = [[[200]], [[100]], [[50]]]
    rgb[:, :, -10:] = [[[200]], [[153]], [[50]]]

    bounds = morecantile.tms.get('WebMercatorQuad').xy_bounds(TILE)
    profile = {
        'driver': 'GTiff',
        'width': SIZE,
        'height': SIZE,
        'dtype': 'uint8',
        'crs': 'EPSG:3857',
        'transform': from_bounds(*bounds, SIZE, SIZE),
        'tiled': True,
        'compress': 'deflate',
    }

    if compress is None:
        with rasterio.open(path, 'w', count=3, nodata=153, **profile) as ds:
            ds.write(rgb)
        return path

    alpha = np.where((rgb == 153).all(axis=0), 0, 255).astype('uint8')
    tmp = path.with_suffix('.rgba.tif')
    with rasterio.open(tmp, 'w', count=4, photometric='RGB', alpha='YES', **profile) as ds:
        ds.write(np.concatenate([rgb, alpha[None]]))
    rio_copy(tmp, path, driver='COG', compress=compress)
    return path


@pytest.fixture
def client(monkeypatch, tmp_path, request):
    path = write_snapshot(tmp_path / 'snapshot.tif', request.param)
    monkeypatch.setattr(fp, 'geotiff_url', lambda _: str(path))
    return TestClient(fp.app)


def get_tile(client, filename, tile=TILE):
    res = client.get(f'/snapshots/abcd1234/{tile.z}/{tile.x}/{filename}')
    assert res.status_code == 200
    assert res.headers['content-type'] == 'image/png'
    assert res.headers['access-control-allow-origin'] == '*'
    return np.asarray(Image.open(io.BytesIO(res.content)).convert('RGBA')).astype(int)


all_formats = pytest.mark.parametrize('client', [None, 'JPEG', 'WEBP'], indirect=True)
legacy_format = pytest.mark.parametrize('client', [None], indirect=True)


@all_formats
def test_tile(client):
    px = get_tile(client, f'{TILE.y}@2x.png')
    assert px.shape == (512, 512, 4)

    # left half fully transparent, right half fully opaque
    assert (px[:, : SIZE // 2 - 2, 3] == 0).all()
    assert (px[:, SIZE // 2 + 2 :, 3] == 255).all()

    # lossy formats are only approximately right
    assert np.abs(px[256, 400, :3] - [200, 100, 50]).max() <= 5
    assert np.abs(px[256, -5, :3] - [200, 153, 50]).max() <= 5


@legacy_format
def test_band_equal_to_nodata_is_not_masked(client):
    px = get_tile(client, f'{TILE.y}@2x.png')
    assert (px[:, -10:] == [200, 153, 50, 255]).all()


@legacy_format
@pytest.mark.parametrize('filename,size', [('{y}.png', 256), ('{y}@2x.png', 512), ('{y}@2x@2x.png', 512)])
def test_tile_sizes(client, filename, size):
    px = get_tile(client, filename.format(y=TILE.y))
    assert px.shape == (size, size, 4)


@legacy_format
def test_tile_outside_bounds(client):
    px = get_tile(client, '0@2x.png', morecantile.Tile(x=0, y=0, z=16))
    assert px.shape == (512, 512, 4)
    assert (px[..., 3] == 0).all()



@legacy_format
def test_zoomed_out_tiles(client):
    # the test snapshot's minzoom is TILE.z
    above = morecantile.Tile(x=TILE.x >> 1, y=TILE.y >> 1, z=TILE.z - 1)
    px = get_tile(client, f'{above.y}@2x.png', above)
    assert (px[..., 3] == 255).any()

    # past the slack, tiles are blank even where the snapshot has data
    below = morecantile.Tile(x=TILE.x >> 2, y=TILE.y >> 2, z=TILE.z - 2)
    px = get_tile(client, f'{below.y}@2x.png', below)
    assert (px[..., 3] == 0).all()

@legacy_format
@pytest.mark.parametrize(
    'path',
    [
        '16/0/99999999.png',
        '25/0/0.png',
        '16/0/0.jpg',
        '16/0/0@3x.png',
        # non-canonical forms of valid coordinates
        f'016/{TILE.x}/{TILE.y}.png',
        f'16/0{TILE.x}/{TILE.y}.png',
        f'16/{TILE.x}/0{TILE.y}.png',
        f'+16/{TILE.x}/{TILE.y}.png',
        f'16/{TILE.x}/+{TILE.y}.png',
        f'16/{TILE.x}/{TILE.y}.0.png',
        '16/' + '1' * 5000 + '/0.png',
        'abc/0/0.png',
    ],
)
def test_invalid_tile(client, path):
    assert client.get(f'/snapshots/abcd1234/{path}').status_code == 404


@legacy_format
def test_tilejson(client):
    res = client.get('/snapshots/abcd1234/index.json')
    assert res.headers['access-control-allow-origin'] == '*'
    tj = res.json()
    bounds = morecantile.tms.get('WebMercatorQuad').bounds(TILE)

    assert tj['tiles'] == ['http://testserver/snapshots/abcd1234/{z}/{x}/{y}@2x.png']
    assert tj['tileSize'] == 512
    assert tj['bounds'] == pytest.approx(list(bounds))
    assert tj['minzoom'] <= TILE.z <= tj['maxzoom']


@pytest.mark.parametrize('snapshot_id', ['abc', 'abcd12345', 'ABCD1234', 'abcd-123'])
@pytest.mark.parametrize('path', ['index.json', '16/0/0.png'])
def test_invalid_snapshot_id(monkeypatch, snapshot_id, path):
    monkeypatch.setattr(fp, 'geotiff_url', lambda _: pytest.fail('looked up an invalid snapshot ID'))
    assert TestClient(fp.app).get(f'/snapshots/{snapshot_id}/{path}').status_code == 404


@pytest.mark.parametrize(
    'url',
    [
        'https://s3.amazonaws.com/files.fieldpapers.org/snapshots/abcd1234/field-paper-abcd1234.tiff',
        'http://s3.amazonaws.com/files.fieldpapers.org/snapshots/abcd1234/walking-paper-abcd1234.tif',
        'https://s3.amazonaws.com/files.fieldpapers.org/snapshots%2Fabcd1234%2Ffield-paper-abcd1234.tiff',
        'https://s3.us-west-2.amazonaws.com/files.fieldpapers.org/snapshots/abcd1234/x.tiff',
    ],
)
def test_geotiff_url(monkeypatch, url):
    monkeypatch.setattr(fp, 'urlopen', lambda *_, **__: io.BytesIO(json.dumps({'geotiff': {'url': url}}).encode()))
    fp.geotiff_url.cache_clear()
    assert fp.geotiff_url('abcd1234') == url


@pytest.mark.parametrize(
    'url',
    [
        '/etc/passwd',
        'file:///etc/passwd',
        '/vsicurl/https://example.com/x.tif',
        'https://example.com/files.fieldpapers.org/x.tif',
        'https://s3.amazonaws.com/other-bucket/x.tif',
        'https://s3.amazonaws.com/files.fieldpapers.org.evil/x.tif',
        'https://s3.amazonaws.com/files.fieldpapers.org/../other-bucket/x.tif',
        'https://s3.amazonaws.com/files.fieldpapers.org/%2e%2e/other-bucket/x.tif',
        'https://s3.amazonaws.com@example.com/files.fieldpapers.org/x.tif',
        'ftp://s3.amazonaws.com/files.fieldpapers.org/x.tif',
    ],
)
def test_geotiff_url_outside_bucket(monkeypatch, url):
    monkeypatch.setattr(fp, 'urlopen', lambda *_, **__: io.BytesIO(json.dumps({'geotiff': {'url': url}}).encode()))
    fp.geotiff_url.cache_clear()
    with pytest.raises(ValueError):
        fp.geotiff_url('abcd1234')
