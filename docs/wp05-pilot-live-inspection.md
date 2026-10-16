# WP05B live pilot: completed output inspection

On 2026-10-16 the owner supplied the completed pilot handoff ZIP (revision 7) and
its downloaded GeoTIFF. The archived raw service response reports `done=true`,
`SUCCEEDED`, attempt 1 and no error. Both computation/file creation and transfer
to the destination are complete in the service metadata.

**The single-tile delivery acceptance passes.** This does not complete the full
Tripoli export or establish model accuracy, full-raster equivalence or runtime for
the whole AOI. No task was submitted, cancelled or resubmitted by this inspection.

## Execution and provenance

- Pilot service commit: `1dbbb180c32d4b23f91643439f90126fadd6dc5c`, package 0.5.1.
- Original mapping engine commit: `bf9cf6c8bbd03d083c2d9bccae722d7036923afc`.
- Server start: `2026-10-16T08:55:16.937107Z`.
- Server end: `2026-10-16T08:58:59.094004Z`.
- Elapsed start-to-end: **222.156897 seconds (3 minutes 42 seconds)**, attempt 1.
- Reported compute usage: 1511.515869140625 EECU-seconds; this is neither elapsed
  wall time nor a monetary cost estimate.

The result used the retained final-map graph. All six stored graph checksums and
the persisted request hash match; the final event equals the handoff job record.
The terminal diagnostic response and ledger agree. The source mapping stays
completed. The TIFF filename matches the export filename prefix, and the file's
dimensions, projection and extent match the exact recorded pilot window.

The uploaded files were read locally; the raster could be opened despite an
earlier attachment-preview error. Raw rasters, graph archives and private Drive
destinations are not committed to this public repository. File digests and
inspection results are recorded in [the machine-readable report](wp05-pilot-live-inspection.json).

## Actual TIFF checks

The complete band and its mask were read with Rasterio/GDAL, not inferred from a
preview or export configuration.

| Property | Observed result |
| --- | --- |
| Dimensions | 1024 × 1024; one band |
| CRS | EPSG:32633 |
| Affine transform | `[10, 0, 371810, 0, -10, 3395680]` |
| Bounds in metres | `[371810, 3385440, 382050, 3395680]` |
| Grid | 10 m north-up; exact integer offsets on the original `[10,0,0,0,-10,0]` lattice |
| Pixel window | column 37181, row −339568, width/height 1024 |
| Data type / NoData | UInt8 / 0 |
| Pixel count | 1,048,576; all valid in this tile |
| Observed class codes | 7 and 8, both within the configured 1–12 domain |
| Mask consistency | Valid-data mask agrees with values unequal to NoData |
| Storage | LZW; 256 × 256 blocks; GDAL reports COG layout |
| Overviews | Factors 2, 4, 8, 16, 32; reported nearest-neighbour resampling |
| File size | 104,684 bytes |

Counts by code are recorded only as an encoding/nonempty-output check. No
interpretation of classification accuracy or suitability is made. There are no
NoData-valued pixels in this fully overlapping tile, so the live inspection does
not exercise a boundary/masked tile. A comprehensive standalone COG conformance
validator was not run; COG layout is reported by GDAL.

## What this establishes and the next decision

One bounded export from the selected graph can complete and deliver an aligned,
nonempty GeoTIFF in this case. It establishes a working path from retained graph
to downloadable raster. It does not support multiplying this runtime by a tile
count, or claiming the full task would have been faster under tiling.

The original full-area operation was last recorded in the pilot preparation
snapshot as RUNNING on attempt 2. That snapshot is historical; this inspection
does not query or change its current state. WP05 full-area acceptance remains open.

The next implementation can prepare an aligned grid and a persistent per-tile
manifest with bounded submission concurrency and explicit retry/resume. First
exercise a small batch including different AOI positions and a boundary tile;
inspect coverage, masks, grid joins and actual runtime before launching the whole
grid. No bulk tile campaign has been launched or automatically authorized by
this inspection. GEE reference/model code remain unchanged.
