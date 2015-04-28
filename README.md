# fp-tiler

I am a tile server for Field Papers atlases and snapshots.

## Usage

```bash
API_BASE_URL=http://next.fieldpapers.org/ npm start
```

Or, as a Docker container:

```bash
docker run --rm -p 8080:8080 -e API_BASE_URL=http://next.fieldpapers.org/ fieldpapers/tiler
```

## Installation

This is a typical npm-managed install, except that
[node-gdal](https://github.com/naturalatlas/node-gdal) must be built from
source in order to support FP's old JPEG-compressed snapshots.

```bash
npm install --build-from-source=gdal
```

To build a Docker image:

```bash
docker built -t fieldpapers/tiler --rm .
```
