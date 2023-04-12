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

This is a typical npm-managed install:

```bash
npm install
```

To build a Docker image:

```bash
docker built -t fieldpapers/tiler --rm .
```

## Quick links
- [🔗 fieldpapers.org](https://fieldpapers.org)
- [📋 Project overview](https://github.com/fieldpapers)
- [🐞 Issues and bug reports](https://github.com/fieldpapers/fieldpapers/issues)
- [🌐 Translations](https://explore.transifex.com/fieldpapers/fieldpapers/)
- [🤝 Code of Conduct](https://wiki.openstreetmap.org/wiki/Foundation/Local_Chapters/United_States/Code_of_Conduct_Committee/OSM_US_Code_of_Conduct)
