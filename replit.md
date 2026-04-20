# PROEVO image background removal app

## Overview
Flask app for uploading images, removing their background with remove.bg, adding PROEVO branding, and saving processed outputs into a dark visual inventory catalog.

## Structure
- `main.py`: Flask routes for the home page, background removal, and processed image catalog.
- `templates/index.html`: Main visual-library interface with scanner upload, search/filter controls, stats, and catalog layout.
- `static/script.js`: Frontend upload, drag/drop, download, search/filter, grid/list view, and catalog-loading behavior.
- `static/logo.png`: PROEVO logo used in the page and processed image branding.
- `static/processed/`: Runtime folder for processed PNG outputs.
- `artifacts/mockup-sandbox/`: Isolated React/Vite canvas preview sandbox for PROEVO layout variations.
- `artifacts/mockup-sandbox/src/components/mockups/proevo-layouts/`: Current baseline plus three inventory layout mockup variants.

## Runtime
Development runs with `python3 main.py` on port `5000`.
Production publishing is configured to run `gunicorn --bind=0.0.0.0:5000 --reuse-port main:app`.
Canvas layout previews run through the `artifacts/mockup-sandbox: Component Preview Server` workflow.

## Secrets
- `REMOVE_BG_API_KEY`: Required for remove.bg background removal.
