# LOD1_2024_PL
All Polish buildings from the 2024 LOD1 pack from GUGiK, stored in a compressed file format.

## File Structure Overview

```
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
| --- | --- | --- |
| `0..3` (`char[4]`) | `magic` | `"GBLD"` |
| `4` (`u8`) | `version` | `2` |
| `5` (`u8`) | `flags` | Bit 0 (`0x01`): DEFLATE enabled |
| `6` (`u8`) | `xy_step_cm` | Horizontal step ($xy$) in cm |
| `7` (`u8`) | `z_step_cm` | Vertical step ($z$) in cm |
| `varint` | `tile_count` | Total tile count |

---

## 2. Indices

### Tile Table Entry
Repeated `tile_count` times:
* `d_origin_x_m` (`svarint`), `d_origin_y_m` (`svarint`): Origin delta vs previous tile (meters)
* `extent_x_m` (`varint`), `extent_y_m` (`varint`): Bounding box width/height (meters)
* `building_count` (`varint`): Buildings in tile

### Block Table Index
Starts with `block_count` (`varint`), followed by `block_count` entries:
* `tiles_in_block` (`varint`): Tiles in block
* `block_meta` (`varint`): `(stored_length << 1) | is_deflated`

---

## 3. Stream Block Layout

When uncompressed (raw DEFLATE, `wbits=-15`), each block contains 6 streams: `[anchor_x, anchor_y, base_z, heights, rings, vertices]`. Each stream begins with a `varint` byte-length header.

1. **`anchor_x` / `anchor_y`** (`svarint` per building): Delta vs previous building in grid steps. Resets to 0 per tile.
2. **`base_z`** (`svarint` per building): Delta vs previous building elevation.
3. **`heights`**: `palette_n` (`varint`) $\rightarrow$ palette values (`varint`) $\rightarrow$ per-building `palette_index` (`varint`).
4. **`rings`**: Per building: `ring_count` (`varint`), then per ring: `(n << 2) | (is_hole << 1) | is_ortho` (`varint`).
5. **`vertices`**:
   * For secondary rings: initial vertex delta (`svarint` $dx, dy$) vs previous ring start.
   * **Plain ring** ($\text{is\_ortho}=0$): $(n-1)$ delta pairs (`svarint` $dx, dy$).
   * **Ortho ring** ($\text{is\_ortho}=1$): `(k << 1) | swap` (`varint`) $\rightarrow$ $(n-2)$ step scalars (`svarint`).

---

## 4. Coordinate Decoding Formulas

$$
\text{spm} = \frac{100}{\text{xy\_step\_cm}}
$$

$$
X_{\text{m}} = \text{tile\_origin\_x\_m} + \frac{x_{\text{grid}}}{\text{spm}}
$$

$$
Y_{\text{m}} = \text{tile\_origin\_y\_m} + \frac{y_{\text{grid}}}{\text{spm}}
$$

$$
Z_{\text{base\_m}} = \text{base\_z} \times \frac{\text{z\_step\_cm}}{100}
$$

$$
Z_{\text{roof\_m}} = Z_{\text{base\_m}} + \left(\text{height} \times \frac{\text{z\_step\_cm}}{100}\right)
$$