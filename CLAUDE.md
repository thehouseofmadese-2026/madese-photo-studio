# Madese Photo Studio — project context

Local Python **Streamlit** app that turns one House of Madese product photo into styled variants
(lifestyle shots, clean listing photos, social/reel thumbnails) using Gemini's image-editing models.
No git repo, not deployed — runs only on this machine.

**Unrelated to bedswap or Term Call Companion.** Related to House of Madese only as its "back room"
tool for the same shop — deliberately reuses that storefront's visual palette by design, but is a
separate codebase with no functional dependency; don't read House of Madese's memory for this project.

## How to run it
```
cd "C:\Users\mayan\OneDrive\Desktop\Madese Photo Studio"
.venv\Scripts\streamlit.exe run app.py --server.headless true --server.port 8501
```
Open `http://localhost:8501`. `GEMINI_API_KEY` is read from a local `.env` file (never hardcoded).

## What's in here
- `app.py` — the Streamlit UI
- `prompts.json` / `prompts_store.py` — the prompt library, one saved "instruction" per style idea,
  editable entirely through the UI, with optional reference images
- `gemini_client.py` — Gemini API calls
- `.streamlit/config.toml` + a custom CSS block in `app.py` — the visual theme (see below)

## Design/taste notes
- Visual identity intentionally reuses House of Madese's real palette: `#FAFAF7` paper, `#16150F` ink,
  `#FF5A1F` molten (the only accent, reserved for the primary action), Anton for headings, Space
  Grotesk for body/UI, Space Mono only for technical strings (model tag). Flat hairline borders, no
  soft SaaS-card shadows, a tactile button-press effect, a thin repeating "layer-line" divider per tab
  (echoing 3D-print layers). Progress-bar copy matches the brand's voice ("Warming up the printer…" /
  "Printing: …" / "Printed").
- Mayank wants tools he uses daily to feel good/distinct, not just functional — don't default to
  generic Streamlit/SaaS chrome here; keep leaning on the real brand identity.

## Full history
Detailed UI/visual work log lives in this project's own memory folder (`madese-photo-studio.md`) —
read it before non-trivial UI changes, not the global memory index.
