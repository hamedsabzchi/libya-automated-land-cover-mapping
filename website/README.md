# Separate website adapter

Start at [app.py](../app.py). Visitor and deployment instructions are in
[docs/website.md](../docs/website.md).

| File | Responsibility |
| --- | --- |
| [ui.py](ui.py) | Google sign-in, visitor settings, saved results, map and legend |
| [service.py](service.py) | Validate settings, isolate worker calls, format saved metrics |
| [worker.py](worker.py) | Initialize Earth Engine with this visitor's token/project and call the unchanged engine |

Do not add a global cached Earth Engine client, ambient credential fallback or
shared result store. The working Colab interface lives in `libya_landcover/`
and is independent of this website.
