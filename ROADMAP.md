# Hubble Workbench Roadmap

This roadmap starts after the v2.0.1 modularization pass on `v2.0.1-development`.

## Phase 2 - Observatory Explorer

Goal: make the Observatory Explorer tab the place where a user can understand what data exists for a target before downloading or composing.

### Observation Explorer

- Summarize observations by mission, instrument, wavelength bucket, exposure, and sky-coordinate availability.
- Highlight the most useful observations and products for RGB work.
- Explain what appears complete, what is missing, and which button should be used next.

### Sky Mosaic Viewer

- Improve the current coordinate map into a clearer sky coverage view.
- Keep the first version as a center-point map using MAST coordinates.
- Later: use true footprint polygons when reliable `s_region` data is available.
- Add optional color modes over time: mission, instrument, wavelength bucket, and exposure.

### Completeness Analyzer

- Check whether blue, green, and red candidates exist.
- Check whether a complete RGB set appears to come from the same alignment group.
- Prefer enhanced products such as drizzle, mosaic, combined, and JWST i2d products.
- Explain a recommended next action in plain language.

## Phase 3 - Multi-Telescope Projects

Goal: support target projects that combine data and context from multiple observatories.

Initial sources:

- Hubble / HST: active
- James Webb / JWST: active
- DSS reference imagery: planned
- Pan-STARRS context imagery: planned
- Chandra: planned X-ray context layer

Later sources:

- GALEX
- WISE
- Additional observatories as useful APIs and workflows are identified

## Phase 4 - NASA Image Wizard

Goal: create a guided workflow that can choose good datasets and build a polished image with less manual work.

Planned capabilities:

- Intelligent dataset selection
- Automatic or guided registration/alignment
- Guided RGB/LRGB composition
- Product-quality explanations
- Saved project notes explaining what data was used and why

### Phase 3 Foundation

- Added `hubble_workbench_app/observatory_sources.py` as the source registry for active and planned observatories.
- Observatory Explorer reports now show active versus planned multi-telescope sources.
- Added a project-plan section that explains loaded active sources and planned context layers.
- Added layer readiness checks for active sources, including observations, products, RGB coverage, and next action.
- Saved structured project state in Observatory Explorer diagnostics for future multi-telescope project tools.
- Added a project checklist that turns layer status into immediate next actions.
- Added activation requirements for planned Chandra, Pan-STARRS, and DSS layers.
- Added an Observatory Explorer action to prepare the best RGB layer from loaded products.
- Added a sky mosaic layer selector for all active sources, Hubble, and JWST.
- Planned sources are visible for project tracking but are not searched yet.

## Current Implementation Notes

Phase 2 begins in `hubble_workbench_app/observatory_workflow.py`. The first implementation step improves the Observatory Explorer report so it gives clearer observation/product summaries and recommended next actions. The Sky Mosaic Viewer now has clearer grid labels, marker sizing, and a legend while still using MAST observation-center coordinates. The Completeness Analyzer now reports a plain-English checklist for RGB coverage, alignment confidence, enhanced products, wider context, and next actions.