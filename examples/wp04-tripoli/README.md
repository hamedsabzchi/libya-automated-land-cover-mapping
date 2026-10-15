# WP04 Tripoli execution case

These exact identifiers were supplied by the repository owner for the live WP04
case. They are configuration, not verified asset-access or execution results.

- Project: `practical-proxy-441422-n6`
- Region: `projects/practical-proxy-441422-n6/assets/Libya/Tripoli`
- Training: `projects/practical-proxy-441422-n6/assets/Libya/TD3-attept1-tripoli`

`case.json` keeps the existing request defaults explicit. The training path spelling
`TD3-attept1-tripoli` is intentional: it is copied exactly from the owner. The field
`lc_code`, 2024 target, five-year window, 2023 fallback, 0.7 split and 500 trees are
the existing defaults; their suitability is not being reassessed. The engine's
normal preflight checks the actual asset/schema when an authorized run starts.

## Open the prepared notebook

[Open Tripoli execution in Colab](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/feat/wp04-installable-runner/python/03_wp04_tripoli_execution.ipynb)

Use a fresh runtime and execute cells 1–5 in order. Cell 2 performs the normal Google
Earth Engine login on the owner's account. Cells 3–4 read the region, construct the
probe plan and execute the pinned engine. Cell 5 downloads only this run's output
folder as ZIP, including partial logs when available. Cell 6 is optional and disabled
by default; enable it only after producing the GEE evidence JSON described there.

The notebook pins engine commit `bf9cf6c8bbd03d083c2d9bccae722d7036923afc` rather
than installing a moving branch. That commit contains the already tested WP04 engine
package; the notebook itself is a later addition. A new request UUID and output
directory are generated for each attempt. No existing run directory is reused.

Probe locations are generated **after** authorized access from the actual region's
WGS84 bounds: a 5 by 5 grid including bounds edges, plus the geometry centroid.
The centroid's UTM zone defines the explicit 10 m grid with transform
`[10, 0, 0, 0, -10, 0]`. Some locations may be outside the region; both class values
and masks are observed. This is a bounded comparison plan, not a sampling method
for estimating map accuracy. It neither modifies the model nor adds training data.
The same saved probe file is supplied to Python and the reference session generator.

The ZIP contains `input/`, `run/` when started, and the generated `reference-session.js`
when prepared. It excludes credentials and the rest of the Colab filesystem. Results
remain private runtime outputs unless the owner chooses to share them. No live output
or training-feature IDs are committed to this public repository by this setup.

## Current status

The owner has now supplied the first completed Python execution bundle. Its
request/status/result linkage, captured observations and graph checksums passed
inspection; see the [run review](../../docs/wp04-tripoli-run-review.md). The separate
GEE evidence and comparison remain pending. No claim of execution parity is made.
The original `case.json` status describes the setup template, not the later run.

The committed notebook retains empty outputs and execution counts. Offline checks validate its
Python syntax, exact asset configuration and probe construction; they do not simulate
a completed live run. See [WP04 execution instructions](../../docs/wp04-execution.md)
for bundle meanings, comparison limits and remaining live acceptance work.
