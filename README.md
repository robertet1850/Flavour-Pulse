# FLAVOUR PULSE V4 — Live Evidence + Local AI

Local F&B/flavour intelligence prototype for Robertet Asia.

## Core capabilities
- Public RSS/Atom ingestion + linked public pages
- CSV/XLSX/PDF/TXT research import
- Public URL import
- Local SQLite evidence archive
- Local Ollama analysis; no OpenAI/Gemini API key
- Broad food, beverage and foodservice taxonomy
- Launch → flavour → profile → concept/format → consumer → occasion → market analysis
- Signal and whitespace generation

## Setup
Install Ollama, then run:
`ollama pull qwen3:8b`
`ollama serve`

Then in this folder:
`pip install -r requirements.txt`
`streamlit run app.py`

Or double-click `run_flavour_pulse.bat`.

## Important
"Live" means the tool refreshes accessible/permitted public sources when you ask it to.
It is not an unrestricted crawler and does not bypass paywalls, logins, robots rules,
copyright restrictions or rate limits. For high-volume global launch intelligence,
licensed data feeds/APIs should be added in a production deployment.

Your internal database and analytical workflow can be proprietary to your environment;
third-party source content remains subject to its own terms/licensing.

## Suggested workflow
1. Refresh public sources.
2. Import your internal launch exports and research files.
3. Ask a focused market/category/flavour question.
4. Review observed evidence versus inference.
5. Export the signal table.
6. Turn strongest signals into Robertet customer concepts.

## V5 roadmap
Entity resolution • flavour ontology/graph • trend velocity • source scoring • scheduled
refresh • team login/shared DB • customer workspaces • automated PPTX/PDF reporting.
