# WP04 Tripoli — first Python execution bundle review

## Status

The owner supplied a completed Python execution bundle on 2026-10-15. Inspection
confirms internally consistent completed status, saved results and captured Python
observations. The separate GEE evidence is absent, so implementation equivalence
has **not** yet been established. WP04 remains open.

This review concerns execution and artifact integrity only. It does not assess,
reinterpret or change the model's scientific accuracy, metrics or selection rule.

## Evidence reviewed

- Archive: `wp04-tripoli-20261015T122033Z-40bc63e0.zip`
- Archive SHA-256: `643009ab90bb81750e6a00b952da53ee786579c1f0b28220d05a4c2935b46c50`
- Executed engine commit recorded in the bundle:
  `bf9cf6c8bbd03d083c2d9bccae722d7036923afc`.
- Project and exact region/training identifiers match the owner's
  [Tripoli configuration](../examples/wp04-tripoli/case.json).

The uploaded archive, raw feature IDs, graph payloads, numerical metric tables and
point coordinates are not republished here. This document records aggregate
execution facts and the checks performed on the supplied files. The reviewer did
not independently authenticate to EE or rerun the model during this inspection.

## Recorded execution

| Item | Observed value |
| --- | --- |
| Bundle state | `completed` |
| Evidence state | `captured` |
| Terminal engine status | `completed`, no recorded terminal error |
| Engine status interval | 12:20:56–12:30:36 UTC on 2026-10-15; approximately 9 min 40 sec |
| Status snapshots | 19, with consecutive validated transitions |
| Seed attempts announced | All 14 configured seeds, in reference order |
| Selected seed | `4444` |
| Selection stop reason | `seeds_exhausted` |
| Normalized feature IDs recorded | 1,184 |
| Selected training / validation ID counts | 826 / 358 |
| Graph artifacts | One final map plus five annual maps, 2020–2024 |
| Raster observation locations | 26, with values and masks for final and annual maps |
| Observation grid | EPSG:32633; affine transform `[10, 0, 0, 0, -10, 0]` |

The status interval ends when the adapter returns its selected result, before the
additional evidence queries; it is not a measurement of the whole Colab session.
An announced attempt is not proof that every candidate succeeded: per-candidate
outcome history is not present in this bundle. `seeds_exhausted` is a normal
selection stop reason with a selected result, not an engine failure.

The six stored map artifacts are serialized EE graphs, not exported GeoTIFFs.
The separate probe evidence includes evaluated class/mask values at the 26 locations;
this does not imply that all pixels have been exported or compared.

## Integrity checks passed

1. WP02 request/status/result validation and identity, fingerprint and timestamp
   linkage passed. All status transitions validate, beginning at revision 0 and
   ending at revision 18, matching the separately saved final status.
2. The input and run requests are equal. Saved engine settings match the resolved
   request. Python evidence configuration, selected result and metrics agree with
   the result record; the raster specification equals the saved probe plan.
3. All six artifact IDs resolve in the saved index, belong to the recorded run,
   and have matching SHA-256 checksums. Their graph files parse as JSON.
4. The bundle's engine, adapter and contracts source fingerprints match the tested
   source files at the recorded engine revision. Commit provenance remains the
   caller's declaration, supported by these matching fingerprints.
5. The entire generated diagnostic session equals the original reference bytes
   followed by the expected separate observer and this exact probe plan. The pinned
   GEE SHA-256 remains
   `1383cb783d6245031be3bce34af9ca7bc7f2952c5e02725b41f21cc75f9819e4`.
6. The Python observation record passes the WP04 evidence schema checks, including
   required raster class/mask fields and probe IDs. No Python record was substituted
   for a missing GEE record.

## Next action: capture the GEE side for this same case

Use the `reference-session.js` already inside this archive in a temporary Earth
Engine Code Editor script. Enter the exact project/assets and model settings from
`input/engine-settings.json`, execute the original RUN button, then click
**WP04: capture execution observations** once that run completes.

Save the complete printed JSON string, without console labels or surrounding
string quotes, as `gee-evidence.json` and provide it alongside the existing Python
bundle. Keep the same asset contents and probe plan. The existing Python evidence
can be reused for comparison; do not start another Python run just to upload the
GEE file. If asset contents changed between runs, record that fact before comparing.

The reviewer can then run the offline `compare` command using these two actual
evidence records. Agreement establishes only the recorded case and probe scope;
fallback, multi-feature ROI and other relevant acceptance observations remain
separate work as described in [WP04 execution](wp04-execution.md).
