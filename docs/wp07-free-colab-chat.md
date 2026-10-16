# WP07 — simple English chat in Colab, without a paid API

The default path now uses a small language model **inside the user's Colab
runtime**. It does not request an OpenAI key, call a hosted inference provider,
require Colab Pro, or rent a server. The user's laptop displays the notebook;
the chat model runs in Colab. The desktop installer is deferred.

Open [the single-start notebook](../python/07_wp07_free_english_assistant.ipynb).
This is the only notebook needed for the current assistant workflow. The earlier
notebooks are developer/history entry points, not prerequisites for users.

## First use — no code editing or previous files

1. Click **Start assistant**. Setup and chat loading happen automatically; wait
   for the app to appear in the same cell.
2. Click **Connect Google** and complete sign-in with an authorized account.
3. Choose the year and click **Review my map**, then **Start mapping**.
4. Use **Check progress**. When mapping finishes, **Prepare sample download**
   appears. Review its scope and click **Create sample file**.
5. Use **Check progress** until the Google Drive link appears. Open it to download
   the sample TIFF. The sample is a small window, not the whole study area.

English chat remains on this page throughout. No ZIP upload is required for a new
map. **Save work for later** downloads a recovery file; next session, open the
same notebook and expand **Continue saved work (optional)** to reopen it. Raw
identifiers, data paths, reports and saved-work selection are under **Details and
support**. Only applicable actions are visible; Google connection and review are
separate from execution. Changing the year invalidates the old review.

The configured profile uses Hamed's Tripoli project/assets. Other users need
authorized access or a coordinator-provided profile with their own project, AOI
and training data. GitHub visibility does not grant GEE asset/project access.
Google sign-in also does not create those permissions. This stage does not change
the user's existing Earth Engine access or billing arrangements.

## English interaction and controls

- All new notebook instructions, labels, tool responses and previews are English.
- Free text proposes the same bounded actions as the existing service. There is
  no generated Python, shell execution, hidden model change or implicit approval.
- The model emits a proposed intent; the existing validation and explicit Run
  boundary remain authoritative. Invented asset paths, years not stated by the
  user, and invented job IDs are rejected by the local parser.
- Replies about jobs/results are assembled from actual records. The language model
  does not invent completed work, area statistics, download destinations or ETAs.
- Direct buttons work without language-model generation. Raw UUIDs, provenance
  and JSON are available under **Technical details**, not required for normal use.
- The UI stays inside notebook widgets: no Gradio server, tunnel, shared endpoint
  or bypass of the notebook interface. Each user has their own runtime.

## Local language model

Default: `Qwen/Qwen2.5-1.5B-Instruct`, revision
`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, Apache-2.0 model license.
The model is downloaded from its publisher's public repository, not bundled into
the Python wheel or result archives. Loading uses safetensors, disables remote
Python code, and does not require a Hugging Face token. Inference uses Transformers
4.57.6, a compatible PyTorch installation, and CPU or an available CUDA GPU.

Only model-file downloads contact Hugging Face; chat inference is local to the
runtime. The application never falls back to OpenAI or another paid provider.
If loading fails, the interface explicitly switches to **Chat could not load** and
retains its buttons. That is not advertised as successful free-text chat. Rerunning
Start assistant retries model loading; an already loaded model is reused.

The model is small and can misunderstand a request. Check the proposed year,
boundary and training data. A rejected/invalid model reply creates no job and asks
the user to rephrase or use the direct controls. This is a task-specific assistant,
not a promise of general ChatGPT-level conversation.

## Resource and delivery limits

Free Colab resources are limited and not guaranteed. CPU replies can take tens of
seconds; the UI displays a working indicator and disables repeated clicks while
processing. GPU availability and exact response time depend on the session. If
Colab stops providing resources, this version cannot guarantee continued service.
It does not request payment or bypass Colab restrictions.

Keep the runtime connected while the Python mapping worker is running. Download
the completed mapping/pilot backup before leaving; after a reset, click Start assistant
and reopen that saved-work file. A submitted GEE export and its recorded identity can be
recovered through the existing pilot handoff. An active Python mapping cannot be
restored from a completed-result ZIP.

The reference GEE script, Python model, adapter and WP02 contracts remain unchanged.
This work does not reassess model accuracy, add bulk tiling, deliver the complete
region, calculate class areas, or perform change analysis.

## Verification

**0.7.1 verification:** 125 offline tests and 9 repository checks passed. The built
wheel was exercised outside the source checkout: single-cell startup, Google
connection callback and asset checks, loaded-model reuse, rerun review invalidation,
and visible chat-load fallback passed with network, authentication and inference
mocked. User-side Colab rendering and live Google login still need checking.

The 0.7.1 simplification adds a fresh-user widget journey that starts with an empty
store, connects, reviews, queues exactly one map, follows completion to a sample,
confirms exactly one export, shows its destination, and saves recovery in the same
UI. Remote mapping/export results and authentication are mocked in this test.
Additional checks cover review invalidation on year change, first-visit status,
reopening existing work, disabled old interfaces, and the single startup cell.
The initial real-model evidence below still applies to the unchanged inference
implementation; the language model was not benchmarked again for this UI change.


On 2026-10-16, **119 offline tests** and **9 repository checks** passed. All 13
protected reference/model/adapter/contract files retained their earlier hashes.
The built 0.7.0 wheel was exercised outside the source checkout with the actual
successful pilot ZIP: widget upload, English status/results, report, backup and
fresh-store reimport passed with network blocked. Notebook startup was tested with
model loading and Google authentication mocked, including loaded-model reuse,
explicit guided fallback and the connection-before-Run boundary.

Separately, the actual pinned Qwen weights were downloaded and run on CPU with
Transformers 4.57.6 and PyTorch 2.14.1+cpu. Six requests returned usable intents;
the unsupported cropland-area question triggered the safe rephrase fallback.
Replies took approximately 19–36 seconds on that test environment. See the
[recorded seven-case smoke test](wp07-local-model-smoke.json). This is not a
general conversation-quality benchmark or a promise of Colab speed.

Offline tests cover the existing engine/job contracts plus local intent validation,
unmentioned-input rejection, safe failure, English previews, upload controls,
connection gating and single-confirmation execution. Real local-model smoke tests
are recorded separately from mocked unit tests. Notebook/browser OAuth behavior
and CPU/GPU performance in the user's actual Colab session still require a first
user-side check; local results are not a guarantee for every runtime.

Primary references:
- [Colab FAQ: resources, runtime lifecycle and notebook interaction](https://research.google.com/colaboratory/faq.html)
- [Publisher's model card and license](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)

