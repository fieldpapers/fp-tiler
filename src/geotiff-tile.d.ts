declare module 'geotiff-tile' {
  import { GeoTIFF } from 'geotiff';

  interface TileOptions {
    geotiff: GeoTIFF;
    bbox_srs: number;
    bbox: number[];
    tile_height: number;
    tile_width: number;
    geotiff_srs: number;
    tile_srs: number;
    use_overview: boolean;
    tile_array_types: string[];
    tile_no_data: number;
  }

  interface TileResult {
    tile: [Int16Array | number[], Int16Array | number[], Int16Array | number[]];
  }

  export default function createTile(options: TileOptions): Promise<TileResult>;
}
