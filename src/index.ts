import { Hono, Context } from 'hono';
import { handle } from 'hono/aws-lambda';
import sharp from 'sharp';
import proj4 from 'proj4';
import createTile from 'geotiff-tile';
import { fromArrayBuffer, GeoTIFF } from 'geotiff';
import { bboxToTile, tileToBBOX } from '@mapbox/tilebelt';
import { LRUCache } from 'lru-cache';
import { S3Client, GetObjectCommand } from '@aws-sdk/client-s3';

const geotiffCache = new LRUCache<string, Promise<GeoTIFF>>({
  max: Number(process.env.GEOTIFF_CACHE_COUNT) || 50
});

const minZoom = 0;
const maxZoom = 24;
const tileSize = Number(process.env.TILE_SIZE) || 512;

const apiBaseUrl = process.env.API_BASE_URL || 'https://fieldpapers.org';
const publicUrl = process.env.PUBLIC_URL;
const s3Client = new S3Client({});

const app = new Hono();

app.use('*', async (c, next) => {
  const start = Date.now();
  await next();
  const duration = Date.now() - start;
  console.log(`${c.res.status} ${c.req.method} ${c.req.path} ${duration}ms`);
});

app.get('/health', (c) => {
  return c.json({ status: 'ok' });
});

interface SnapshotMetadata {
  geotiff: {
    url: string;
  };
}

async function fetchSnapshotGeotiff(id: string): Promise<GeoTIFF> {
  const response = await fetch(`${apiBaseUrl}/snapshots/${id}.json`);
  const json = (await response.json()) as SnapshotMetadata;

  const s3Url = new URL(json.geotiff.url);
  let bucket: string;
  let key: string;

  if (s3Url.hostname === 's3.amazonaws.com' || s3Url.hostname.match(/^s3[.-].*\.amazonaws\.com$/)) {
    const pathParts = s3Url.pathname.slice(1).split('/');
    bucket = pathParts[0];
    key = pathParts.slice(1).join('/');
  } else {
    bucket = s3Url.hostname.split('.')[0];
    key = s3Url.pathname.slice(1);
  }

  const command = new GetObjectCommand({ Bucket: bucket, Key: key });
  const s3Response = await s3Client.send(command);

  if (!s3Response.Body) {
    throw new Error('Empty S3 response body');
  }

  const bytes = await s3Response.Body.transformToByteArray();
  const arrayBuffer = bytes.buffer as ArrayBuffer;
  return await fromArrayBuffer(arrayBuffer);
}

function getSnapshotGeotiff(id: string): Promise<GeoTIFF> {
  const cached = geotiffCache.get(id);
  if (cached) return cached;

  const promise = fetchSnapshotGeotiff(id).catch((err) => {
    geotiffCache.delete(id);
    throw err;
  });

  geotiffCache.set(id, promise);
  return promise;
}

async function getSnapshotBounds(id: string): Promise<[number, number, number, number]> {
  const geotiff = await getSnapshotGeotiff(id);
  const image = await geotiff.getImage();
  const projBounds = image.getBoundingBox();
  const sw = proj4('EPSG:3857', 'EPSG:4326', [projBounds[0], projBounds[1]]);
  const ne = proj4('EPSG:3857', 'EPSG:4326', [projBounds[2], projBounds[3]]);
  return [sw[0], sw[1], ne[0], ne[1]];
}

async function getSnapshotTileJson(id: string, baseUrl: string) {
  const bounds = await getSnapshotBounds(id);
  const smallestTileZoom = bboxToTile(bounds)[2];
  const center: [number, number, number] = [
    (bounds[2] + bounds[0]) / 2,
    (bounds[3] + bounds[1]) / 2,
    Math.min(smallestTileZoom + 4, maxZoom)
  ];

  const tileSuffix = tileSize === 512 ? '@2x.png' : '.png';

  return {
    name: `fp-snapshot-${id}`,
    minzoom: Math.min(smallestTileZoom + 2, maxZoom),
    maxzoom: Math.min(smallestTileZoom + 9, maxZoom),
    bounds,
    center,
    tiles: [`${baseUrl}/snapshots/${id}/{z}/{x}/{y}${tileSuffix}`],
    tileSize,
    format: 'png',
    tilejson: '2.0.0'
  };
}

async function generateTileForSnapshot(
  id: string,
  z: number,
  x: number,
  y: number,
  tileSize: number
): Promise<Buffer> {
  if (z > maxZoom || z < minZoom) {
    throw new Error(`Zoom ${z} is invalid`);
  }

  const maxCoord = Math.pow(2, z) - 1;
  if (x < 0 || x > maxCoord || y < 0 || y > maxCoord) {
    throw new Error(`Tile coordinates ${x},${y} are invalid for zoom ${z}`);
  }

  const geotiff = await getSnapshotGeotiff(id);
  const bbox = tileToBBOX([x, y, z]);

  const tile = await createTile({
    geotiff,
    bbox_srs: 4326,
    bbox,
    tile_height: tileSize,
    tile_width: tileSize,
    geotiff_srs: 3857,
    tile_srs: 3857,
    use_overview: false,
    tile_array_types: ['Array', 'Int16Array'],
    tile_no_data: -1
  });

  const [r, g, b] = tile.tile;
  const channels = 4;
  const pixelCount = r.length;
  const rawImageData = new Uint8Array(pixelCount * channels);

  for (let i = 0; i < pixelCount; i++) {
    const offset = i * channels;
    rawImageData[offset] = r[i];
    rawImageData[offset + 1] = g[i];
    rawImageData[offset + 2] = b[i];
    rawImageData[offset + 3] = r[i] < 0 ? 0 : 255;
  }

  return sharp(rawImageData, {
    raw: {
      width: tileSize,
      height: tileSize,
      channels: 4
    }
  })
    .toFormat('png')
    .toBuffer();
}

app.get('/snapshots/:snapshotId/index.json', async (c) => {
  try {
    const snapshotId = c.req.param('snapshotId');
    const baseUrl = publicUrl || new URL(c.req.url).origin;
    const data = await getSnapshotTileJson(snapshotId, baseUrl);
    return c.json(data);
  } catch (err) {
    console.error('Error generating TileJSON:', err);
    return c.json(
      {
        error: {
          message: err instanceof Error ? err.message : 'Internal server error',
          status: 500
        }
      },
      500
    );
  }
});

app.get('/snapshots/:snapshotId/:z/:x/:filename', async (c) => {
  try {
    const snapshotId = c.req.param('snapshotId');
    const z = parseInt(c.req.param('z'), 10);
    const x = parseInt(c.req.param('x'), 10);
    const filename = c.req.param('filename');
    const y = parseInt(filename.replace(/(@2x)?\.png$/, ''), 10);

    if (isNaN(z) || isNaN(x) || isNaN(y)) {
      throw new Error('Invalid tile coordinates');
    }

    const tileSizeForRequest = filename.endsWith('@2x.png') ? 512 : 256;
    const data = await generateTileForSnapshot(snapshotId, z, x, y, tileSizeForRequest);

    return c.body(data as Uint8Array<ArrayBuffer>, 200, {
      'Content-Type': 'image/png',
      'Cache-Control': 'public, max-age=31536000, immutable'
    });
  } catch (err) {
    console.error('Error generating tile:', err);
    return c.json(
      {
        error: {
          message: err instanceof Error ? err.message : 'Internal server error',
          status: 500
        }
      },
      500
    );
  }
});

export const handler = handle(app);
