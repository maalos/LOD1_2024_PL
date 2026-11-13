# LOD1_2024_PL

All Polish buildings from the 2024 LOD1 pack from GUGiK, stored in a compressed file format.

## File Structure Overview

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

- `d_origin_x_m` (`svarint`), `d_origin_y_m` (`svarint`): Origin delta vs previous tile (meters).
- `extent_x_m` (`varint`), `extent_y_m` (`varint`): Bounding box width/height (meters).
- `building_count` (`varint`): Buildings in tile.

### Block Table Index

Starts with `block_count` (`varint`), followed by `block_count` entries:

- `tiles_in_block` (`varint`): Tiles in block.
- `block_meta` (`varint`): `(stored_length << 1) | is_deflated`.

---

## 3. Stream Block Layout

When uncompressed (raw DEFLATE, `wbits=-15`), each block contains 6 streams:

```text
[anchor_x, anchor_y, base_z, heights, rings, vertices]
```

Each stream begins with a `varint` byte-length header.

### 3.1. Anchor Coordinates

`anchor_x` / `anchor_y` (`svarint` per building):

- Delta vs previous building in grid steps.
- Resets to 0 per tile.

### 3.2. Base Elevation

`base_z` (`svarint` per building):

- Delta vs previous building elevation.

### 3.3. Heights

```text
palette_n (varint)
palette values (varint)
per-building palette_index (varint)
```

### 3.4. Rings

Per building:

```text
ring_count (varint)
```

Then, per ring:

```text
(n << 2) | (is_hole << 1) | is_ortho
```

The encoded value is stored as a `varint`.

### 3.5. Vertices

For secondary rings:

- Initial vertex delta (`svarint dx, dy`) vs previous ring start.

**Plain ring** (`is_ortho = 0`):

- `(n - 1)` delta pairs (`svarint dx, dy`).

**Ortho ring** (`is_ortho = 1`):

```text
(k << 1) | swap (varint)
```

Followed by:

- `(n - 2)` step scalars (`svarint`).

---

## 4. Coordinate Decoding Formulas

### 4.1. Horizontal Grid Resolution

The number of grid steps per meter:

```text
spm = 100 / xy_step_cm
```

### 4.2. Horizontal Coordinates

Convert grid coordinates into coordinates in meters:

```text
X_m = tile_origin_x_m + x_grid / spm
Y_m = tile_origin_y_m + y_grid / spm
```

Where:

- `tile_origin_x_m`, `tile_origin_y_m`: Tile origin coordinates in meters.
- `x_grid`, `y_grid`: Decoded building coordinates in grid steps.
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
- `height`: Building height in vertical grid steps.
- `z_step_cm`: Vertical resolution in centimeters.

---

## 5. Compression

- Blocks can be stored raw or DEFLATE-compressed.
- Compression is indicated by the `is_deflated` bit in `block_meta`.
- DEFLATE decompression must use raw mode (`wbits = -15`).

