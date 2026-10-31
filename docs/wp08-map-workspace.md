# WP08 — Map workspace

## User path

Open [the single-cell Colab](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/feat/wp08-map-workspace/python/08_wp08_map_workspace.ipynb) and click **Start assistant**. Installation and the first local chat-model download take time. No API key is needed.

1. **Connect.** Click **Connect Google** and follow the authentication prompt. Your account needs authorized Earth Engine access to the configured project, boundary and training assets. Public repository access does not grant asset access.
2. **Prepare map.** Choose a year, click **Create map** once. Keep Colab connected during preparation. Repeating the same request reuses an existing queued, running or completed map instead of starting another seed search.
3. **Explore & download.** When preparation finishes, the interface requests the full study-area land-cover layer automatically. Use zoom, pan, the layer control, the boundary and the legend. A basemap alone is not a classified result. If colours stay blank, use **Open / reload map** and check the visible error message. Complex retained graphs may exceed interactive Earth Engine limits; this version does not automatically create a cached raster asset or claim that every display tile rendered.
4. Click a blue grid square. The selected square is outlined in gold. Click **Create tile download** once. The selected cell, year and resolution are shown before that click. Status updates about every 20 seconds while connected and idle. You can continue exploring while the server creates the TIFF. Select additional tiles individually; no bulk campaign starts automatically.
5. When ready, use **Open result in Google Drive** to get the TIFF. **Save work for later** saves recovery metadata and retained model graphs, not pixels. Next time, open this same notebook and use **Continue saved work**. An unfinished Python map-preparation worker cannot be restored after the runtime is deleted. A submitted Earth Engine export is separate from the notebook session.

**Details and support → Saved work** selects an earlier map or download in the current session. **Save work for later** preserves all completed mapping bundles, all export observations and recorded support evidence in one workspace ZIP. An unfinished model process is retained as evidence and cannot be restarted from that archive.

## When to use chat

Everything essential is available through buttons. Expand **Ask the assistant** when you want help:

| English request | Result |
| --- | --- |
| What do the colours mean? | Explains the exact 12-class reference legend. |
| What should I do next? | Gives a next step based on the selected job. |
| Is my map ready? | Checks the selected job; queries the server for a live export when connected. |
| Prepare a map for Tripoli for 2024. | Prepares a review card, or reopens an existing matching job. |
| Change the year to 2023. | Changes the pending mapping proposal; review it again. |
| Show my map. | Opens the selected completed map's display layer. |
| Download the selected tile. | Prepares a review card for the tile selected on the map. |

New messages and tile choices invalidate the previous review confirmation. A chat message never submits a map or export. The free local model parses general mapping requests; map-specific shortcuts and tool responses are grounded in the actual selection and stored jobs. There is no class-area calculation, change analysis or unrestricted GIS conversation in this release.

## Implementation boundaries

- `gee/automated_land_cover_app.js`, `python/landcover_engine.py`, `python/assistant_adapter.py` and the request/result contracts are unchanged. The reference file SHA-256 remains `1383cb783d6245031be3bce34af9ca7bc7f2952c5e02725b41f21cc75f9819e4`.
- `MapBackend` restores the retained final-map graph. `getMapId` receives that image clipped to the actual AOI, never the former pilot window. Only the visible boundary is simplified (100 m tolerance); classification clipping uses the original geometry. Palette and class labels match the reference exactly.
- Display uses Earth Engine web-map tiles in `ipyleaflet`. Map URLs are ephemeral runtime values and are not persisted in reports or recovery archives. The map and local language model run without an external chat server or tunnel.
- Download cells are aligned 1024 × 1024 pixel windows in EPSG:32633, with `[10,0,0,0,-10,0]`. Adjacent windows share edges. Clicking selects a cell; preparation checks positive overlap with the actual AOI. It does not verify unmasked raster pixels or automatically skip interior empty cells. Outside-AOI pixels are NoData (0), following the existing export implementation.
- Only the visible grid is sent to the browser, capped at 400 cells. Zoom in to see denser grids; location clicks can still select a cell when the overview grid is hidden for size. The download grid is separate from the web-map display tiling.
- Selected tiles use the existing persisted export and recovery services. Repeated confirmation cannot launch the same draft twice. Automatic polling never submits or retries a job. The selected classifier graph can be recomputed by Earth Engine for display/export; retained graphs are not precomputed raster assets.
- Generic asset/parameter changes and classifier redesign are outside this UI change. No model-accuracy assessment was added.

## Verification and live acceptance

Offline tests cover the reference legend, adjacent grid bounds, bounded viewport grids, real Earth Engine client serialization of full-AOI display and selected-tile export, outside-AOI rejection, duplicate-map prevention, confirmation invalidation, recovery, actual widget event handlers, automatic polling and old-notebook upgrade. Tests do not use live Google credentials or submit exports.

Live acceptance remains to be performed in an authorized Colab session: connect, open a completed retained map (or prepare one), see coloured land cover across the actual study area with the legend, select a non-centroid tile, confirm its export, and receive its Drive TIFF. Check that an outside-AOI tile is rejected and reopening the same year does not create another mapping job. Browser rendering, current Colab resources, chat quality and full-area interactive latency cannot be established by offline tests. A successful earlier pilot does not establish these new display checks.

The implementation is provided on `feat/wp08-map-workspace`, stacked on WP07, for review; no merge into `main` is implied.

## Display troubleshooting (0.8.1)

A completed mapping job means its retained graphs are saved; it does not guarantee that the interactive layer opened. If the map stays on the basemap, do not rerun mapping. **Open / reload map** now shows the failure stage, exception type and server message in an expanded **Error details** panel. **Details and support → Save error / details** saves this diagnostic when a display error is present. Temporary URLs and authorization values are omitted.

The stage distinguishes restoring the saved map, requesting the land-cover layer, reading the boundary, and building the notebook map interface. The UI no longer suggests a permission problem for every exception. The exact cause of the reported live display failure remains unconfirmed until its diagnostic is available. This patch does not change the model or automatically submit an export. Updating the Start assistant cell in the same connected runtime preserves the completed job files.

## Incomplete Colab viewport messages (0.8.2)

`TraitError: The east trait ... expected a float ... None` can be reproduced by sending `Map.set_state({'east': None})`, without authenticating or calling Earth Engine. It describes the browser widget viewport, not the AOI asset bounds. In the pinned ipyleaflet 0.20.0 frontend, `update_bounds` begins with infinite east/west values when no Leaflet view is available; JSON transport can represent these as null. Source: https://github.com/jupyter-widgets/ipyleaflet/blob/0.20.0/python/jupyter_leaflet/src/Map.ts .

The workspace now uses a small `NotebookMap` subclass. It ignores an incoming geographic/pixel viewport group containing null or nonfinite numbers, preserving the last numeric values, and accepts subsequent valid updates. Float traits remain nonnullable; no fake coordinate or AOI change is introduced. Grid drawing falls back to the actual AOI extent if there is no valid viewport yet. Updating or closing the workspace explicitly closes the old map comm, including when upgrading from 0.8.1.

Regression tests reproduce the reported exception on an ordinary Map, exercise invalid then valid browser messages on NotebookMap, verify the saved mapping/AOI and submission counts are unchanged, and check map-comm cleanup during upgrade. This fixes the reproduced widget-state error; it does not establish that the earlier Earth Engine display request succeeded. If the layer still cannot open, use the separate Error details panel added in 0.8.1.

## Collection-shaped AOI display (0.8.3)

The live diagnostic identified `Geometry.coordinates: GeometryCollections do not have coordinate lists` in `read_study_area_boundary`. The display code now retrieves the complete simplified, WGS84 GeoJSON geometry with `getInfo()` and passes it unchanged into the outline Feature. A GeometryCollection retains its `geometries` members, including nested collections; Polygon and MultiPolygon keep their coordinates. Extent calculations still use the bounds polygons. The model graph, exact AOI clipping and tile overlap/export operations are unchanged.

Regression checks cover Polygon and nested GeometryCollection responses, ensure the outline query never invokes `Geometry.coordinates`, instantiate the actual ipyleaflet GeoJSON layer, and verify saved graph bytes remain identical. Live rendering with the user's private AOI still needs confirmation. The fix reopens a completed map without submitting another mapping/export job.


## Plain map background (0.8.4)

The live Colab screenshot showed OpenStreetMap 403 / Access blocked tiles behind a partially loaded land-cover layer. The workspace now creates its map with an empty layer list, avoiding the implicit OpenStreetMap basemap entirely. It uses Leaflet's plain background; no alternative paid provider, proxy, or key is introduced. The Earth Engine raster attribution, study-area outline, legend, grid, selection and download behavior are retained. Blank areas are not claimed as completed raster coverage.

The UI regression checks that no TileLayer is present before connection and that only the original Earth Engine raster is present after opening and reloading. Grid selection remains tested. This removes the OSM background dependency; it does not change Earth Engine compute quotas or guarantee that all raster tiles have finished loading. The reference GEE, Python model and stored graphs are unchanged.


## Guided completion path (0.8.5)

A visible **Next step** message follows connection, map preparation, tile selection, review, export progress and delivery. Map-preparation status and tile-download status have separate headings. The tile confirmation card appears directly below the map/selected tile; the map-preparation review stays next to year selection. Completed exports without a returned URI show the recorded Drive folder instead of inventing a link.

An offline widget integration test follows a saved map through connection, tile selection, explicit confirmation, real export-service state transitions backed by a fake remote server (PENDING → RUNNING → SUCCEEDED), Drive-link display, duplicate-request reuse and ZIP save/reimport in a fresh assistant. It confirms one remote start and no mapping launch. Another test checks the no-URI folder fallback. These are software checks, not a live Google Drive download or a full rendering check. The user's screenshot establishes partial raster display, not complete coverage. The earlier live pilot exports remain the only confirmed TIFF deliveries reported in this chat.

Remaining user acceptance: open the updated notebook with the saved-work ZIP, see colours and the legend, select one tile inside the boundary, confirm its export once, and download its actual TIFF from Drive. Earth Engine restricted mode may slow this; updating the UI does not reset compute quota. No classifier, GEE reference, adapter, contract or export algorithm is changed by this patch.


## Consistent status and blank-layer diagnostics (0.8.6)

The latest screenshot shows an AOI outline with no visible classified pixels and conflicting preparation guidance. It does not establish why the raster is blank; the compute-quota warning alone does not establish a particular tile failure.

The UI now reads one selected-job summary per refresh for status and next-step guidance. Mapping state comes from the same summary, avoiding separate ledger reads that can disagree during worker completion. Mounting a layer immediately synchronizes navigation, zoom controls and legend. A regression test checks a stale running observation alongside a completed summary. This addresses the reproduced software inconsistency, not every possible asynchronous Colab rendering issue.

**Check map display** makes one explicit HTTP request from Colab for the map-centre tile at the current zoom using the already-issued Earth Engine URL. It uses connect/read timeouts, a 64 KiB response-read limit, no retries and no redirects. It does not rebuild the model or start an export. Like viewing a tile, it can consume Earth Engine compute. URLs and headers are not saved; service error messages are sanitized. PNG data is evidence for that one request, not proof of colours, browser rendering or full coverage. Timeout alone does not diagnose quota exhaustion.

The result appears beneath the map toolbar. **Details and support → Save error / details** downloads it when no other interface error is active. Raster requests are bounded to the study-area bounding box, with world wrapping disabled. The original exact image clipping and model are unchanged.

Live check: reopen saved work, centre the map inside the boundary, click **Check map display** once and share the diagnostic. Do not create the map again. Development tests use simulated server responses; no live tile request or full rendering was verified here.


## Failed preparation evidence (0.8.7)

A user run failed before map display. Its pasted status did not include the underlying engine error, so the cause of that live run is unconfirmed. This patch fixes missing failure evidence; it does not claim to fix that unknown failure.

Failed/interrupted mapping jobs now show an expanded error panel and a directly visible **Download failure report** button. Empty map controls are hidden for failed preparation. Reports include recorded engine status and a whitelist of runner-manifest failure fields. Future initialization, engine and runner failures retain a bounded sanitized exception chain in the local manifest, without changing reference GEE, the Python model/adapter or retry behavior. Older runs may have only a type/code because discarded exception details cannot be reconstructed.

Tests exercise failure capture and the actual failure-report button without launching another mapping or export. Offline checks do not establish live model execution. For the already-failed 0.8.6 session, first download **Details and support → Save error / details** and share the JSON before updating, deleting the runtime or retrying. The original session contains evidence that another notebook cannot automatically access.


## Blank-widget recovery (0.8.8)

The latest live screenshot shows a completely empty map, including no boundary or grid; a separate one-tile HTTP check timed out. These observations do not identify the browser's underlying failure or prove that quota is the cause.

Map mounting now creates a fresh widget with all four layers already attached and an initial study-area viewport. It avoids the previous sequence of separate add/remove messages and the asynchronous fit loop waiting for browser bounds. **Restore map display** rebuilds that widget from its cached outline, grid, selection and existing tile URL, without asking the backend to recreate the layer or starting a mapping/export. Viewing it can still make Earth Engine tile requests. The button retains a selected tile and any review awaiting confirmation. A stale or timed-out server tile URL is not fixed by rebuilding the widget.

Selection, download and confirmation controls are above the map. Technical display diagnostics start collapsed. The one-time `python/repair_map_display.py` helper installs the pinned display update in the current Colab runtime, replaces only display modules and remounts the existing assistant. It retains the current store, jobs, chat model and Google connection; it does not reset the runtime or rerun the engine. Run it in the existing session, not a new notebook runtime.

Regression tests simulate a map with missing layers, restore all layers and selection, retain an existing review, and check that no backend/map/export launch occurs. Actual Earth Engine colours and full-area rendering still require evidence from the user's Colab session. No reference, model, adapter or contract changes.


## Unified delivery workflow (0.9.0)

The user reported that no download link appeared. The current remote task result was not supplied, so its exact server outcome remains unknown. Code inspection found several concrete UI failure paths: clicks could be silently dropped during background polling, links were rendered only for the selected job, imported unfinished observations did not automatically attach to live operations, and submissions without an operation name were skipped.

The main workflow is now **Connect Google → Create map → select a square → Create tile download**. The map and export buttons each confirm their displayed choices in one click. Selection and chat never submit work by themselves. Existing pending reviews remain usable after an in-session update. Duplicate clicks reuse the existing mapping/export identity.

A permanent **Downloads** section retains every export, including when another map or tile is selected. Background checks start on connection and wake after an action. They reconcile unknown submissions and attach imported operations without creating new tasks. A busy background read no longer drops the user's confirmation. Failed preparation/export shows its recorded reason. Completed exports without a returned destination get an explicitly labelled Drive folder search, not an invented direct download URL; the original operation is queried up to three times for a late destination. Read failures preserve the previous job state. Mapping and export algorithms, reference GEE, Python engine, adapter and contracts remain unchanged.

The workspace ZIP contains checked completed graphs, export metadata/history, failed-run evidence and the escaped conversation history. It does not contain raster pixels or credentials, does not restore uploaded SQL/code, and does not revive executable approvals in a new session. Legacy full-region export records are retained as read-only/recoverable references; no full-region campaign is automatically started. ZIP import validates graph checksums and export identities before creating any recovered records. Older single-result ZIPs remain supported. Checkpoints update locally when job revisions change. **Save work for later** downloads the complete checkpoint; local autosaving cannot survive deletion of the Colab runtime unless the ZIP is downloaded.

`python/update_workspace.py` updates the existing runtime once, waits for in-flight activity, pauses polling, installs the pinned package, writes/downloads a pre-update workspace backup, then replaces the interface while retaining the assistant, store, job IDs, credentials, chat model, selection, pending review and transcript. It restarts automatic status checks and never restarts the classifier or submits an export. A new user only needs the single-cell notebook. Rerunning that notebook in the same session reuses the existing workspace instead of clearing its pending choices.

Verification uses explicit simulated Earth Engine responses, blocked sockets and blocked cloud-credential discovery. It exercises one-click submission, duplicate prevention, clicks during polling, lost submission reconciliation, imported-job tracking, persistent completed links, late destination/folder fallback, error reporting, all-work ZIP round trips, malformed archive rejection and in-place updates. Live acceptance still requires the user's authenticated export to reach SUCCEEDED and its Drive TIFF to be accessible; local tests do not establish that remote outcome or full-area colour coverage.


## Colab status delivery (0.9.1)

The user's live worker report for job `004e3ed4-7c71-4379-82bb-3a9b3160462b` confirms completed preparation without error at 2026-10-31T11:08:04Z. Its page still showed queued, although its Python polling task existed. This establishes a stale display, not a failed mapping or an export failure. The exact kernel/browser cause was not observed directly.

Colab has a documented report of background widget updates not reaching the frontend (googlecolab/colabtools issue 3373). The workspace now registers a read/display-only Colab callback and uses the visible output's JavaScript timer to request a refresh every five seconds. It explicitly resends the widget tree, reads saved mapping status and opens a completed map in the active callback context. It does not depend on an idle asyncio task to publish those changes. Existing export observations use the same reconciliation code, at most one remote check per 20 seconds. Calls are sequential; busy UI work is not overlapped. No map or export submission, retry or cancellation is performed by the callback.

The timer stops on page exit, a closed workspace or three consecutive callback transport failures. Replacing the UI unregisters its prior callback. Ordinary non-Colab notebooks retain asyncio polling. The current runtime updater retains all job identities, selected tile, pending review, chat and work files, and displays a saved map during the update when Google is connected. Original GEE, classifier, adapter and contracts are byte-identical.

Regression coverage includes a stale queued page whose worker has completed while no asyncio task executes, one-time map mounting, a completed export's visible Drive link, repeated ticks without new submissions, pending-choice preservation, callback replacement and busy/closed guards. JavaScript timer tests cover one outstanding callback, retries and retirement. These are simulated/offline checks, not proof of delivery in the user's current Colab browser. The existing live report proves model preparation only; the new browser display and selected-tile TIFF still require user-side confirmation.
