# WP08 — Map workspace

## User path

Open [the single-cell Colab](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/feat/wp08-map-workspace/python/08_wp08_map_workspace.ipynb) and click **Start assistant**. Installation and the first local chat-model download take time. No API key is needed.

1. **Connect.** Click **Connect Google** and follow the authentication prompt. Your account needs authorized Earth Engine access to the configured project, boundary and training assets. Public repository access does not grant asset access.
2. **Prepare map.** Choose a year, click **Review my map**, then **Create map**. Keep Colab connected during preparation. Repeating the same request reuses an existing queued, running or completed map instead of starting another seed search.
3. **Explore & download.** When preparation finishes, the interface requests the full study-area land-cover layer automatically. Use zoom, pan, the layer control, the boundary and the legend. A basemap alone is not a classified result. If colours stay blank, use **Open / reload map** and check the visible error message. Complex retained graphs may exceed interactive Earth Engine limits; this version does not automatically create a cached raster asset or claim that every display tile rendered.
4. Click a blue grid square. The selected square is outlined in gold. Click **Download selected tile**, review it, and click **Create tile download**. Status updates about every 20 seconds while connected and idle. You can continue exploring while the server creates the TIFF. Select additional tiles individually; no bulk campaign starts automatically.
5. When ready, use **Open result in Google Drive** to get the TIFF. **Save work for later** saves recovery metadata and retained model graphs, not pixels. Next time, open this same notebook and use **Continue saved work**. An unfinished Python map-preparation worker cannot be restored after the runtime is deleted. A submitted Earth Engine export is separate from the notebook session.

**Details and support → Saved work** selects an earlier map or download in the current session. Saving one download preserves that selected export and its parent map, not every export in the session. Save each active download you need to recover before ending the runtime.

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
