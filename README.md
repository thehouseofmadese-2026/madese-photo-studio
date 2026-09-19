# Madese Photo Studio

A local Streamlit app that turns one product photo into multiple styled
variants — lifestyle shots, clean white-background listing photos, and
bold social/reel thumbnails — using Gemini's image-editing models.

**Model picker.** A dropdown in the sidebar ("Model") picks which Gemini
image model is used for your *next* Generate click — pick per generation,
not a fixed setting:

| Model | Cost/image | Best for |
|---|---|---|
| ⚡ Lite (`gemini-3.1-flash-lite-image`) | ~₹3 | Fast, cheap draft exploration — trying out many style ideas |
| ⚖️ Flash (`gemini-3.1-flash-image`) | ~₹5.7 | Balanced general use |
| ✨ Pro (`gemini-3-pro-image`) | ~₹11.5 | Best text/branding fidelity — final photos for actual Amazon/Etsy listings |

In testing, Lite and Flash both rendered product text/branding small and
flat; Pro rendered it bold, centered, and embossed-looking — worth the extra
cost for photos that'll actually represent the business.

Every input image sent also costs a small amount (your product photo, plus
any reference images attached — see below). Keep reference images to 1–3
per instruction and reasonably sized to keep cost down regardless of model.
(The app previously defaulted to `gemini-2.5-flash-image`, which cost more
per image and is being shut down by Google on October 2, 2026 — none of the
current model options have that problem.)

Nothing is hardcoded: every instruction it sends to Gemini comes from your
own editable library in `prompts.json`, which you build up over time.

## Setup

1. **Install dependencies** (Python 3.10+ recommended):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   pip install -r requirements.txt
   ```

2. **Add your API key.** Copy `.env.example` to `.env` and paste in a key
   from [Google AI Studio](https://aistudio.google.com/apikey):

   ```
   GEMINI_API_KEY=your_key_here
   ```

   The key is only ever read from this file — it's never hardcoded and
   never shown in the UI.

3. **Run it:**

   ```bash
   streamlit run app.py
   ```

## How it works

- **Three tabs** — Lifestyle Shots, Clean Listing Photos, Social/Reel
  Thumbnails — each with its own independent list of instructions.
- **Upload a product photo once** in the sidebar; it's used across whichever
  tab you're working in.
- **Add instructions freely.** In any tab's "Add a new instruction" box you
  can either:
  - **Add to saved list** — saves it to `prompts.json` for reuse later, or
  - **⚡ Add & generate now** — saves it *and* immediately generates with
    just that one instruction.
- **Title each instruction** so long prompts are easy to tell apart at a
  glance — the title field sits right above the instruction text on each
  saved row, and shows above the image in the results gallery too.
- **Edit or delete** any saved instruction in place; edits save back to
  `prompts.json` immediately.
- **Reference images.** Any instruction — new or already saved — can have one
  or more reference images attached (via "🖼️ Reference images" on each saved
  row, or the uploader under "Add a new instruction"). When generating,
  Gemini is told to match the reference image's style/composition/lighting
  while keeping the actual product from your uploaded photo. Best results
  with 1–3 references per instruction.
- **Generate selected** runs only the checked instructions; **Generate All**
  runs every instruction currently in that tab's list.
- **Results gallery** shows every output with a download button. A failed
  call (safety block, network error, etc.) shows an error message in its
  spot instead of crashing the batch.
- **Last used** — whichever instruction(s) you ran most recently on a tab
  are remembered (marked with 🕓 and pre-checked) the next time you open the
  app, so you don't have to re-pick them every session.

## Storage

- `prompts.json` — your instruction library, one entry per tab, plus each
  tab's `last_used` instruction ids. Pre-filled with starter examples; edit
  it by hand or entirely through the UI. Schema:

  ```json
  {
    "<Tab Name>": {
      "instructions": [{
        "id": "abc12345",
        "title": "Cozy Desk Morning",
        "text": "...",
        "reference_images": ["reference_images/Tab_Name/abc12345/xyz.png"]
      }],
      "last_used": ["abc12345"]
    }
  }
  ```

- `outputs/<Tab_Name>/<YYYYMMDD_HHMMSS>/` — every generated PNG from that
  batch, one folder per Generate click.
- `reference_images/<Tab_Name>/<instruction_id>/` — reference images attached
  to each instruction, referenced by relative path from `prompts.json`.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI |
| `gemini_client.py` | Gemini API wrapper (model call, error handling) |
| `prompts_store.py` | Reads/writes `prompts.json` and reference images |
| `prompts.json` | Your instruction library (data, not code) |
| `outputs/` | Generated images |
| `reference_images/` | Reference images attached to instructions |
