# User guide — Libya Land-Cover Assistant

[Project home](../README.md) · [Documentation index](README.md)

## One notebook for the complete workflow

**[Open the assistant in Google Colab](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/python/Libya_Land_Cover_Assistant.ipynb)**

The numbered development notebooks are not a course or a sequence you need to complete. Use the complete notebook above. English chat, maps and downloads are included there.

## Before starting

You need a Google account authorized for the configured Earth Engine project, study-area boundary and training data. The default example is Tripoli. If you are a new project user, the owner must arrange the required access. The region selector is configured for this profile; choosing a different study area is not currently a general self-service upload workflow.

No paid chat API key or external server is required by this notebook. Colab and Earth Engine resource limits still apply. The first local chat-model download may take several minutes.

## Create and explore a map

1. Open the complete notebook and click **Start assistant**. Wait for the interface to open.
2. Click **Connect Google** and complete the sign-in prompt.
3. In **Map settings for your next run**, choose **Target year** and **Fallback year**. Both support 2017–2025. The defaults are 2024 and 2023. The fallback supplies missing target-year embedding data according to the existing engine rules.
4. Click **Create map** once. Follow **Next step** while preparation runs. Changing a year alone does not start work.
5. Explore the coloured map and its legend. Display tiles load as you pan and zoom; a grey area may still be loading.

Preparing a map, displaying its colours and exporting a TIFF are separate operations. A completed preparation means the map definition was saved; it does not prove every visible map tile has loaded.

## Download a selected area

1. Zoom in and select a blue grid square. The selected square is outlined in gold.
2. Check the selected tile and click **Create tile download** once.
3. Follow **Downloads**. Its status updates automatically while the notebook is connected.
4. When complete, open the displayed Google Drive link and download the `.tif` file or files.

Each selected tile is 1024 × 1024 pixels at 10 m resolution (10.24 × 10.24 km). Pixels outside the study area are NoData. You can select additional tiles individually. There is no automatic whole-region download campaign.

## When to use the assistant

Chat is optional: the buttons handle the essential workflow. Use English requests such as:

| Request or button | What it does |
| --- | --- |
| “Explain colours” | Explains the land-cover legend |
| “What should I do next?” | Gives guidance for the current workflow |
| “Status” | Reports recorded job status; automatic checks update active downloads |
| **Model accuracy** / “What is the classification accuracy?” | Reads saved validation results for the selected map |
| **Explain accuracy** / “Interpret accuracy” | Explains the saved metrics |
| “Explain the accuracy of cultivated irrigated land” | Explains that class using the stored report |
| “Which classes are most often confused?” | Summarizes saved confusion-matrix counts |
| “Set target year to 2025 and fallback year to 2024” | Prepares a review; it does not execute a new map by itself |

Check a chat-prepared review before confirming it. The local language model can misunderstand requests. If it cannot load, the interface labels its guided-command mode and the buttons remain available.

Saved accuracy belongs to the model validation run, not to a new assessment of the selected TIFF tile. Reading it does not rerun evaluation. Class-area statistics and change analysis are not currently included.

## Save work and return later

| File | What it contains | Where to get it |
| --- | --- | --- |
| TIFF (`.tif`) | Raster map pixels for the exported tile | The completed download's Google Drive link |
| Saved-work ZIP (`.zip`) | Saved map definitions, download records and recovery information | **Save work for later** |

Before leaving, use **Save work for later**. In a later session, open the same complete notebook, expand **Continue saved work (optional)** and choose **Open saved work** to upload the ZIP. Connect Google to reopen the prepared map or check live exports. You do not need to create a completed map again.

Keep Colab connected during Python map preparation. A deleted runtime cannot resume an unfinished Python mapping process. A submitted Earth Engine export runs separately on Google's servers and can be followed from its saved record. The ZIP does not contain TIFF pixels.

## If something needs attention

| What you see | Next step |
| --- | --- |
| Google/project/asset access error | Ask the project owner to verify the account's access to the configured project and assets |
| Prepared map saved, but colours are absent | Use **Map tools and diagnostics — optional**; **Open / reload map**, **Restore map display** and **Check map display** are available there. Do not recreate a completed map just to restore its display |
| Download is queued or running | Keep the notebook connected and let automatic status checks continue; do not submit the same download repeatedly |
| Download fails or no link is available | Share the download/error details with the project owner; a submission is not a completed TIFF |
| Quota restriction or throttling | Share the message with the project owner; repeatedly creating maps or exports will not restore quota |
| `VBox(...)` text instead of controls | Confirm you opened the current complete Colab, not GitHub's static notebook preview or an older patch notebook. Version 0.12.1 includes the widget-display fix; if it persists, share the visible message and version |

For technical support, use **Details and support** and preserve your saved-work ZIP. [Technical notes and release history](wp08-map-workspace.md) are available for the project maintainer.
