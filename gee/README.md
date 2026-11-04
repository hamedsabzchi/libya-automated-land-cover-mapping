# Original Google Earth Engine reference

[Project home](../README.md) · [Model reference](../docs/model-reference.md)

**[automated_land_cover_app.js](automated_land_cover_app.js)** is the original JavaScript reference application. It remains in its original location and has not been changed by this repository organization.

For the complete English chat/map/download workflow, use the [Colab assistant](../python/Libya_Land_Cover_Assistant.ipynb). This directory is for users and developers who want to inspect or work directly with the Earth Engine JavaScript application.

The reference app accepts accessible AOI and training FeatureCollection asset IDs. Its original target/fallback input range is 2017–2024. The Python assistant separately supports 2017–2025; that extension did not edit this reference file.

| Reference | Purpose |
| --- | --- |
| [GEE behavior specification](../docs/gee-reference-spec.md) | Records the active reference path and settings |
| [Python integration](../docs/python-engine-integration.md) | Documents the port and adapter |
| [Parity checklist](../docs/python-parity-checklist.md) | Tracks reference behavior and software checks |
| [Tripoli comparison](../docs/wp04-tripoli-comparison.md) | Recorded execution observations for a specific case |

The diagnostic helper [libya_landcover/gee_observer.js](../libya_landcover/gee_observer.js) is separate from the reference application.
