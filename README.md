# LOD1_2024_PL

All Polish buildings from the 2024 LOD1 pack of GUGiK (the Head Office of Geodesy and Cartography), stored in a
compact, compressed file format: footprints (with courtyard holes) and heights.

| | |
|---|---|
| Buildings | 15,118,300 |
| Files | 433 (`bld/<NNNN>_<sheet>.bld`, e.g. `0264_M-33.bld`) |
| Size | about 240 MB in total, compressed from around 71 GB |
| Coordinates | EPSG:2180 (PL-1992), metres, **x = easting, y = northing** |
| Precision | 10 cm horizontal (`xy_step_cm = 10`), 10 cm vertical (`z_step_cm = 10`) |

This repository holds a re-encoding of GUGiK's data, not the original CityGML. For the original and for the
authoritative description of the dataset, see the sources below.

## Licence and source

The 2024 LOD1 3D building models are open data of the National Geodetic and Cartographic Resource (PZGiK), published
by GUGiK. According to GUGiK they are available free of charge and without licence restrictions for any use,
including commercial use: no application is needed, and they may be downloaded, processed, modified and used in
private, scientific and commercial projects. They are published under the Geodetic and Cartographic Law and the Act
on open data and the re-use of public sector information.

- GUGiK announcement: <https://www.gov.pl/web/gugik/aktualizacja-modeli-3d-budynkow-w-standardzie-lod1>
- Download page: <https://www.geoportal.gov.pl/pl/dane/inne-dane/modele-3d-budynkow/>

## Quick start

```bash
pip install numpy
python3 lod1_decode.py bld/0264_M-33.bld
# 67484 buildings, 219 holes, median height 8.0 m
```

```python
from lod1_decode import read_buildings

for b in read_buildings("bld/0264_M-33.bld"):
    b["anchor"]    # (x, y) in EPSG:2180 metres: the first vertex of the first ring
    b["height"]    # metres, None when unknown
    b["rings"]     # [(is_hole, array of (x, y) in EPSG:2180 metres, open ring), ...]
```

`lod1_decode.py` is a complete reference decoder (numpy only). `pl1992.py` converts EPSG:2180 to and from WGS84
lon/lat without `pyproj`.

## Coordinate system

All coordinates are **EPSG:2180** (ETRF2000-PL / CS92), in metres, with **x as easting and y as northing**. This is
the opposite of the axis order in the EPSG definition (northing, easting), so mind it when feeding the values to a GIS
library that follows that definition.

PL-1992 is a Transverse Mercator projection on GRS80: central meridian 19°E, scale factor 0.9993, false easting
500000 m, false northing -5300000 m. `pl1992.py` implements it in pure numpy (Krüger series, error below 0.001 mm):

```python
import pl1992
lon, lat = pl1992.to_lonlat(x, y)        # arrays of degrees
x, y = pl1992.from_lonlat(lon, lat)
```

Sanity check: Wrocław's Rynek is near (362294, 362199).

## File structure overview

```text
+-------------------------------------------------------------+
| Global Header                                               |
+-------------------------------------------------------------+
| Tile Table Index                                            |
+-------------------------------------------------------------+
| Block Table Index                                           |
+-------------------------------------------------------------+
| Stream Blocks (Raw or DEFLATE compressed)                   |
+-------------------------------------------------------------+
```

All integers are LEB128 varints. A `svarint` is a varint with zigzag encoding: `(v >> 1) ^ -(v & 1)`.

---

## 1. Global Header

| Offset / Type | Name | Description |
|---|---|---|
| `0..3` (`char[4]`) | `magic` | `"GBLD"` |
| `4` (`u8`) | `version` | `2` |
| `5` (`u8`) | `flags` | Bit 0 (`0x01`): DEFLATE enabled |
| `6` (`u8`) | `xy_step_cm` | Horizontal step (`xy`) in cm |
| `7` (`u8`) | `z_step_cm` | Vertical step (`z`) in cm |
| `varint` | `tile_count` | Total tile count |

---

## 2. Indices

### Tile Table Entry

Repeated `tile_count` times:

- `d_origin_x_m` (`svarint`), `d_origin_y_m` (`svarint`): Origin delta vs previous tile (meters, EPSG:2180; the first
  tile's delta is against 0). The origin is the tile's south-west corner.
- `extent_x_m` (`varint`), `extent_y_m` (`varint`): Bounding box width/height (meters).
- `building_count` (`varint`): Buildings in tile.

Tiles are about 2.2 km wide. Tiles with no buildings are not listed.

### Block Table Index

Starts with `block_count` (`varint`), followed by `block_count` entries:

- `tiles_in_block` (`varint`): Tiles in block. Blocks take the tiles in table order, so block 0 holds the first
  `tiles_in_block` tiles, block 1 the next ones, and so on.
- `block_meta` (`varint`): `(stored_length << 1) | is_deflated`.

The blocks follow the table one after the other, `stored_length` bytes each. A block is the smallest unit that can be
decompressed: to read one tile, decode its whole block (a block can hold dozens of tiles and tens of thousands of
buildings).

---

## 3. Stream Block Layout

When uncompressed (raw DEFLATE, `wbits=-15`), each block contains 6 streams:

```text
[anchor_x, anchor_y, base_z, heights, rings, vertices]
```

Each stream begins with a `varint` byte-length header. The streams run through the block's buildings in tile order,
and within a tile in the order of its building list.

### 3.1. Anchor Coordinates

`anchor_x` / `anchor_y` (`svarint` per building):

- Delta vs previous building in grid steps.
- Resets to 0 per tile.
- The anchor is where the building's first ring starts (its first vertex).

### 3.2. Base Elevation

`base_z` (`svarint` per building):

- Delta vs previous building elevation.
- The decoder here keeps it as a running total from the start of the file's data. Terrain-following consumers do not
  need it: take the ground from a terrain model and use `height` (3.3).

### 3.3. Heights

```text
palette_n (varint)
palette values (varint)
per-building palette_index (varint)
```

A building's height is `palette[palette_index] * z_step_cm / 100` metres. Zero means unknown.

### 3.4. Rings

Per building:

```text
ring_count (varint)
```

Then, per ring:

```text
(n << 2) | (is_hole << 1) | is_ortho
```

The encoded value is stored as a `varint`. `n` is the number of distinct vertices: **rings are stored open**, the
first vertex is not repeated at the end. Add it if your consumer wants a closed ring. The first ring of a building is
its outer ring (counter-clockwise in EPSG:2180); further rings are courtyard holes, or further outer rings.

### 3.5. Vertices

Where a ring starts:

- The first ring starts at the building's anchor.
- Every further ring starts with a delta (`svarint dx, dy`) **relative to the previous ring's start** (not to the
  anchor), in grid steps.

**Plain ring** (`is_ortho = 0`):

- `(n - 1)` delta pairs (`svarint dx, dy`), each relative to the previous vertex.

**Ortho ring** (`is_ortho = 1`): a rectilinear outline in a frame turned by some angle (most buildings are). Stored as

```text
(k << 1) | swap (varint)
```

followed by `(n - 2)` step scalars (`svarint`), in grid steps. Decoding:

1. The frame is turned by `theta = k * (pi / 2) / 16384` radians (`k` is a quarter-turn quantised to 14 bits).
   `u = (cos theta, sin theta)`, `v = (-sin theta, cos theta)`.
2. Edges alternate between two axes. With `swap = 0` the first edge runs along `u`, the second along `v`, the third
   along `u`...; with `swap = 1` the first runs along `v`, then `u`, and so on.
3. Step `i` is the signed length of edge `i` (grid steps), along its axis, which gives vertices `1 .. n - 2`.
4. Vertex `n - 1` is vertex `n - 2` moved along the axis of edge `n - 2` by minus the sum of the steps already taken
   along that axis. The closing edge back to vertex 0 is then along the other axis by construction.

For a rectangle (`n = 4`) that is two steps: width and depth, in the turned frame.

---

## 4. Coordinate Decoding Formulas

### 4.1. Horizontal Grid Resolution

The number of grid steps per meter:

```text
spm = 100 / xy_step_cm
```

### 4.2. Horizontal Coordinates

Convert grid coordinates into coordinates in meters (EPSG:2180, x east, y north):

```text
X_m = tile_origin_x_m + x_grid / spm
Y_m = tile_origin_y_m + y_grid / spm
```

Where:

- `tile_origin_x_m`, `tile_origin_y_m`: Tile origin coordinates in meters.
- `x_grid`, `y_grid`: Decoded building coordinates in grid steps (anchor plus the ring's deltas).
- `spm`: Number of horizontal grid steps per meter.

### 4.3. Base Elevation

Convert the decoded base elevation into meters:

```text
Z_base_m = base_z * (z_step_cm / 100)
```

### 4.4. Roof Elevation

Calculate the roof elevation:

```text
Z_roof_m = Z_base_m + height * (z_step_cm / 100)
```

Where:

- `base_z`: Decoded building base elevation in vertical grid steps.
- `height`: Building height in vertical grid steps (the palette value).
- `z_step_cm`: Vertical resolution in centimeters.

---

## 5. Compression

- Blocks can be stored raw or DEFLATE-compressed.
- Compression is indicated by the `is_deflated` bit in `block_meta`.
- DEFLATE decompression must use raw mode (`wbits = -15`).