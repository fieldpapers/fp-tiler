# fp-tiler

I am a tile server for Field Papers atlases and snapshots.

## Usage

```bash
API_BASE_URL=http://next.fieldpapers.org/ npm start
```

## Installation

This is a typical npm-managed install, except that
[node-gdal](https://github.com/naturalatlas/node-gdal) must be built from
source in order to support FP's old JPEG-compressed snapshots.

```bash
npm install --build-from-source=gdal
```
