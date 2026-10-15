# WP04 Tripoli — Python/GEE observations match

## Result

The supplied Tripoli Python and GEE evidence records produce
`status: observations_match`, with no differing fields and no missing observation
groups. See the [machine-readable comparison](wp04-tripoli-comparison.json).

This confirms agreement for this one configured case and its explicit probe plan.
It does not prove equality of every raster pixel, all possible input cases, or
service behavior on every seed. No model method, reference code or accuracy
evaluation was changed as part of this comparison.

## Inputs and extraction

- Python archive: `wp04-tripoli-20261015T122033Z-40bc63e0.zip`, SHA-256
  `643009ab90bb81750e6a00b952da53ee786579c1f0b28220d05a4c2935b46c50`.
- Owner-supplied GEE console text: `Pasted text(20261015-130609).txt`, SHA-256
  `f8ce0e5198c10f98a68832dc18670e17c77a94530cdd279e5c2e178b789a670d`.
- Engine revision: `bf9cf6c8bbd03d083c2d9bccae722d7036923afc`.
- Pinned GEE SHA-256:
  `1383cb783d6245031be3bce34af9ca7bc7f2952c5e02725b41f21cc75f9819e4`.

The pasted text includes surrounding Code Editor interface/console text and two
complete `wp04.1` GEE JSON objects. Both were extracted with a JSON decoder, validated
and independently compared with the existing Python record. They are identical
objects, so they are treated as one observation record, not evidence of two independent
runs. No missing fields were invented and no Python values were copied into GEE data.

The earlier [Python bundle integrity review](wp04-tripoli-run-review.md) remains
the record of status linkage, graph checksums and exact reference-session verification.
The uploaded raw console text, feature IDs, probe coordinates and metric tables
are not republished here.

## Matching observation groups

| Group | Result |
| --- | --- |
| Actual execution configuration | Same project assets, class field, years and all reference-mode parameters |
| Selected result | Seed `4444`, same selection values and `seeds_exhausted` stop reason |
| Existing numerical outputs | Same overall/kappa/producer values, confusion counts and sampled count |
| Normalized feature IDs | Same 1,184 IDs, compared as sorted lists |
| Training feature IDs | Same 826 IDs, compared as sorted lists |
| Validation feature IDs | Same 358 IDs, compared as sorted lists |
| Raster observation specification | Same 26 locations, EPSG:32633 and exact affine grid |
| Raster classes | All 156 observations equal: 26 locations across final plus five annual maps |
| Raster masks | All corresponding 156 mask observations equal |

The standard comparator allows an absolute numerical tolerance of 1e-9 (relative
tolerance 0) for existing floating output values. A separate direct comparison also
found these numerical values equal without requiring that tolerance. Configuration,
sorted IDs, grid, class values and masks match exactly in the supplied records.

## Observed service error

The GEE console also records:

```text
Seed 778 failed:
Earth Engine memory capacity exceeded.
```

The reference run continued and produced its selected result at seed `4444`; that
selected result matches Python. This is evidence of the reference's continuation
after a candidate failure in this run. The Python bundle logs seed attempts but does
not preserve per-candidate outcomes, so it cannot establish whether Python had the
same seed-specific error. No claim that all candidates succeeded is made. No
parameter change or workaround is introduced to hide this observed service error.

## Acceptance boundary and next work

The ordinary Tripoli execution comparison is complete. No repeat of these same runs
is needed to supply the already matching observation groups.

WP04 remains open for the separately scoped remaining cases: target-year fallback
under missing/partially masked inputs, appropriate multi-feature ROI/clip observations,
and any remaining failure-path coverage needed for acceptance. Full-raster export
and pixelwise comparison were not part of this probe comparison. The report therefore
retains `full_raster_parity_proven: false`.

The next assistant-service work can build on this installable, exercised interface:
durable job management and downloadable map outputs, followed by chatbot tool calls.
Those features are not implemented or deployed by this documentation update.
