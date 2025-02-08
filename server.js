import { readFileSync } from 'fs';
import express from 'express';
import cors from 'cors';
import sharp from 'sharp';
import proj4 from 'proj4';
import createTile from "geotiff-tile";
import { fromArrayBuffer } from 'geotiff';
import { bboxToTile, tileToBBOX } from '@mapbox/tilebelt';
import { LRUCache } from 'lru-cache'
import { dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const geotiffCache = new LRUCache({
  max: 10 // most geotiffs to cache in memory at once
});
const inflightPromises = {};
const app = express();
app.use(cors({
  origin: true
}));

const minZoom = 0;
const maxZoom = 24;

const port = process.env.PORT || 8080;
const siteUrl = process.env.SITE_URL || `http://localhost:${port}`;
const snapshotGeotiffUrlTemplate = process.env.GEOTIFFS_ENDPOINT || `https://s3.amazonaws.com/files.fieldpapers.org/snapshots/$1/field-paper-$1.tiff`;

const viewerHtml = readFileSync(`${__dirname}/snapshot-viewer.html`).toString();

async function getSnapshotGeotiff(id) {
  if (geotiffCache.has(id)) {
    return Promise.resolve(geotiffCache.get(id));
  } else if (inflightPromises[id]) {
    return inflightPromises[id];
  } else {
    const url = snapshotGeotiffUrlTemplate.replaceAll('$1', id);
    const promise = fetch(url)
      .then(res => res.arrayBuffer())
      // Don't use the `fromUrl` constructor because we want to
      // download the data once, cache it, and access it quickly
      // on subsequent calls.
      .then(arrayBuffer => fromArrayBuffer(arrayBuffer, {
        cache: true
      }))
      .then(geotiff => {
        geotiffCache.set(id, geotiff);
        delete inflightPromises[id];
        return geotiff;
      })
      .catch(err => {
        delete inflightPromises[id];
        throw err;
      });
      inflightPromises[id] = promise;
    return promise;
  }
}

async function getSnapshotBounds(id) {
  return getSnapshotGeotiff(id)
    .then(geotiff => geotiff.getImage())
    .then(image => {
      const projBounds = image.getBoundingBox();
      return [proj4('EPSG:3857', 'EPSG:4326', [projBounds[0], projBounds[1]]), proj4('EPSG:3857', 'EPSG:4326', [projBounds[2], projBounds[3]])].flat();
    });
}

async function getSnapshotTileJson(id) {
  return getSnapshotBounds(id)
    .then(wgsBounds => {
      const smallestTileZoom = bboxToTile(wgsBounds)[2];
      const center = [(wgsBounds[2] + wgsBounds[0]) / 2, (wgsBounds[3] + wgsBounds[1]) / 2, Math.min(smallestTileZoom + 4, maxZoom)];

      return {
        name: `fp-snapshot-${id}`,
        minzoom: Math.min(smallestTileZoom + 2, maxZoom),
        maxzoom: Math.min(smallestTileZoom + 9, maxZoom),
        bounds: wgsBounds,
        center: center,
        tiles: [
          `${siteUrl}/snapshots/${id}/{z}/{x}/{y}.png`,
          `${siteUrl}/snapshots/${id}/{z}/{x}/{y}@2x.png`
        ],
        tileSize: 256,
        format: "png",
        tilejson: "2.0.0"
      };
    });
}

async function generateTileForSnapshot(id, z, x, y, tileSize) {

  if (z > maxZoom || z < minZoom) {
    return Promise.reject(new Error(`Zoom ${z} is invalid`));
  }

  return getSnapshotGeotiff(id)
    .then(geotiff => {

      let bbox = tileToBBOX([x, y, z]);

      return createTile({
        geotiff,
        bbox_srs: 4326,
        bbox: bbox,
        tile_height: tileSize,
        tile_width: tileSize,
        geotiff_srs: 3857,
        tile_srs: 3857,
        use_overview: false,
        // need to specify Int16Array so result we can assign a negative "tile_no_data" value
        tile_array_types: ["Array", "Int16Array"],
        tile_no_data: -1,
      });
    })
    .then(tile => {

      let r = tile.tile[0];
      let g = tile.tile[1];
      let b = tile.tile[2];
    
      let channels = 4;
    
      const rawImageData = new Uint8Array(r.length * channels);
      for (let i in r) {
        rawImageData[i*channels] = r[i];
        rawImageData[i*channels + 1] = g[i];
        rawImageData[i*channels + 2] = b[i];
        // we've set the "tile_no_data" value to negative, so make those pixels transparent
        rawImageData[i*channels + 3] = r[i] < 0 ? 0 : 255;
      }
      
      // convert raw pixel data to PNG
      return sharp(rawImageData, {
        raw: {
          width: tileSize,
          height: tileSize,
          channels: 4,
        }
      })
        .toFormat('png')  
        .toBuffer();
    });
}

app.get('/snapshots/:snapshotId([\\d\\w]+)/index.json', (req, res, next) => {  
  getSnapshotTileJson(req.params.snapshotId)
    .then(data => {
      res.set('Content-Type', 'application/json');
      res.send(data);
    })
    .catch(next)
});

app.get('/snapshots/:snapshotId([\\d\\w]+)/:z(\\d+)/:x(\\d+)/:y(\\d+):r((@2x)?).png', (req, res, next) => {
    const z = parseInt(req.params.z, 10);
    const x = parseInt(req.params.x, 10);
    const y = parseInt(req.params.y, 10);
    const tileSize = req.params.r === '@2x' ? 512 : 256;
    
    generateTileForSnapshot(req.params.snapshotId, z, x, y, tileSize)
      .then(data => {
        res.set('Content-Type', 'image/png');
        res.send(data);
      })
      .catch(next)
});

app.get('/snapshots/:snapshotId/', (req, res, next) => {
  getSnapshotBounds(req.params.snapshotId)
    .then(bounds => {
      let html = viewerHtml;
      html = html.replaceAll('{{SNAPSHOT}}', req.params.snapshotId);
      html = html.replaceAll('{{BOUNDS}}', `[[${bounds[0]},${bounds[1]}],[${bounds[2]},${bounds[3]}]]`);
      res.set('Content-Type', 'text/html');
      res.send(html);
    })
    .catch(next)
});

app.listen(port, function() {
  console.log(`Listening on port ${port}`);
});
