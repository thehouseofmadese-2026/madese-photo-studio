"""
Madese Photo Studio — turn one product photo into styled variants using
Gemini's image-editing model, with a fully editable, JSON-backed prompt
library per tab.

Run with: streamlit run app.py
"""
import os
import time
from datetime import datetime

import streamlit as st
from PIL import Image
from dotenv import load_dotenv

import prompts_store as store
from gemini_client import generate_variant, GeminiImageError, MODEL_OPTIONS, DEFAULT_MODEL

load_dotenv()

st.set_page_config(page_title="Madese Photo Studio", page_icon="📸", layout="wide")

# ---------------------------------------------------------------- visual identity
# Same palette/type as the House of Madese storefront — this tool is the same
# shop's back room, not a separate SaaS product. One accent (molten orange)
# does the work of saying "this is the important button"; everything else
# stays quiet paper/ink so that one color keeps meaning something.
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Anton&family=Space+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap');

:root{
  --paper:#FAFAF7; --ink:#16150F; --molten:#FF5A1F; --marigold:#FFD23F;
  --signal:#2B4BFF; --line:rgba(22,21,15,.14);
}

html, body, [data-testid="stAppViewContainer"], .stApp{
  font-family:'Space Grotesk', sans-serif; color:var(--ink);
}

/* Display type — the brand's poster face, used only for real headings */
h1, h2, h3, [data-testid="stHeading"] h1, [data-testid="stHeading"] h2, [data-testid="stHeading"] h3{
  font-family:'Anton', sans-serif; letter-spacing:.01em; font-weight:400;
}
[data-testid="stHeading"] h1{ font-size:2.6rem; margin-bottom:0; }
p.app-tagline{
  font-family:'Space Grotesk', sans-serif; color:rgba(22,21,15,.65);
  font-size:1rem; margin-top:2px; margin-bottom:1.4rem;
}

/* Sidebar reads as a control strip, not a generic panel */
[data-testid="stSidebar"]{ border-right:2px solid var(--ink); }
[data-testid="stSidebar"] h2{ font-size:1.15rem; }

/* Flat, hard-edged chrome instead of soft SaaS-card shadows */
[data-testid="stVerticalBlockBorderWrapper"]{
  border:1.5px solid var(--line) !important; border-radius:12px !important;
  box-shadow:none !important; background:#FFFFFF;
}
[data-testid="stExpander"]{
  border:1.5px solid var(--line) !important; border-radius:12px !important;
  box-shadow:none !important;
}
[data-testid="stExpander"] summary{ font-weight:600; }

/* Buttons: flat ink outline, a small tactile "print-stamp" press */
.stButton>button, .stDownloadButton>button{
  border:2px solid var(--ink) !important; border-radius:10px !important;
  font-weight:600 !important; box-shadow:none !important;
  transition:transform .08s ease, background .15s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover{ border-color:var(--molten) !important; }
.stButton>button:active, .stDownloadButton>button:active{ transform:translateY(1px); }
.stButton>button[kind="primary"]{ border-color:var(--ink) !important; }

/* Softened dividers */
hr{ border-color:var(--line) !important; }

/* One signature flourish per tab — a print-farm layer line, used sparingly */
.layer-rule{
  height:10px; margin:.4rem 0 1.1rem 0; opacity:.5; border-radius:3px;
  background:repeating-linear-gradient(-45deg, var(--ink) 0 2px, transparent 2px 7px);
}

/* Technical strings (model tag, counts) get the mono face; prose doesn't */
.tag-mono{ font-family:'Space Mono', monospace; font-size:.78rem; color:rgba(22,21,15,.6); }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def layer_divider():
    """A thin repeating-line rule — the print farm's own visual signature,
    used once per tab rather than everywhere, so it stays a flourish."""
    st.markdown('<div class="layer-rule"></div>', unsafe_allow_html=True)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
TABS = store.TABS

MODEL_LABELS = [f"{label} ({price})" for _, label, price in MODEL_OPTIONS]
LABEL_TO_MODEL = {f"{label} ({price})": mid for mid, label, price in MODEL_OPTIONS}
MODEL_TO_SHORT_LABEL = {mid: label for mid, label, price in MODEL_OPTIONS}
DEFAULT_MODEL_LABEL = next(
    (lbl for lbl in MODEL_LABELS if LABEL_TO_MODEL[lbl] == DEFAULT_MODEL), MODEL_LABELS[0]
)

# ---------------------------------------------------------------- session state
if "prompts_data" not in st.session_state:
    st.session_state.prompts_data = store.load()
if "results" not in st.session_state:
    st.session_state.results = {tab: [] for tab in TABS}

data = st.session_state.prompts_data

# ---------------------------------------------------------------- helpers
safe_folder_name = store.safe_folder_name


def load_reference_images(rel_paths):
    """Load an instruction's saved reference-image paths as PIL Images, skipping
    any that have gone missing on disk."""
    images = []
    for rel in rel_paths or []:
        abs_path = os.path.join(BASE_DIR, rel)
        if os.path.exists(abs_path):
            try:
                images.append(Image.open(abs_path).convert("RGB"))
            except Exception:
                pass
    return images


def attach_uploaded_references(tab: str, instruction_id: str, uploaded_files):
    for uf in uploaded_files or []:
        try:
            ref_img = Image.open(uf).convert("RGB")
            store.add_reference_image(data, tab, instruction_id, ref_img)
        except Exception as e:
            st.warning(f"Couldn't use reference image {uf.name}: {e}")


def run_generation(tab: str, targets: list, source_image):
    """targets: list of {"id", "text"} dicts. Calls Gemini once per target,
    saves every successful image to /outputs, updates the gallery, and
    records which instructions were used as this tab's 'last_used'."""
    if source_image is None:
        st.warning("Upload a product photo in the sidebar first.")
        return
    if not targets:
        st.warning("Nothing to generate — that list is empty.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(OUTPUTS_DIR, safe_folder_name(tab), timestamp)
    os.makedirs(out_dir, exist_ok=True)

    selected_model = LABEL_TO_MODEL.get(st.session_state.get("model_select"), DEFAULT_MODEL)
    product_context = st.session_state.get("product_context", "")

    results = []
    progress = st.progress(0.0, text="Warming up the printer…")
    for i, item in enumerate(targets):
        progress.progress(i / len(targets), text=f"Printing: {item['text'][:60]}…")
        entry = {
            "id": item["id"],
            "title": item.get("title", ""),
            "text": item["text"],
            "image_path": None,
            "error": None,
            "model": selected_model,
        }
        try:
            ref_images = load_reference_images(item.get("reference_images")) or None
            result_image = generate_variant(
                source_image,
                item["text"],
                reference_images=ref_images,
                model=selected_model,
                product_context=product_context,
            )
            file_path = os.path.join(out_dir, f"{i + 1:02d}_{item['id']}.png")
            result_image.save(file_path)
            entry["image_path"] = file_path
        except GeminiImageError as e:
            entry["error"] = str(e)
        except Exception as e:  # belt-and-suspenders — never let one bad call kill the app
            entry["error"] = f"Unexpected error: {e}"
        results.append(entry)
    progress.progress(1.0, text="Printed")
    time.sleep(0.15)
    progress.empty()

    st.session_state.results[tab] = results
    store.set_last_used(data, tab, [t["id"] for t in targets])

    failures = [r for r in results if r["error"]]
    if failures:
        st.error(f"{len(failures)} of {len(results)} generation(s) failed — see details below.")
    else:
        st.success(f"Generated {len(results)} image(s). Saved to outputs/{safe_folder_name(tab)}/{timestamp}/")


def render_tab(tab: str):
    tab_data = data[tab]
    instructions = tab_data["instructions"]
    last_used = set(tab_data.get("last_used", []))

    st.subheader(tab)
    layer_divider()

    # --- add a brand-new instruction ---
    with st.expander("➕ Add a new instruction", expanded=len(instructions) == 0):
        new_title = st.text_input(
            "Title",
            key=f"newtitle_{tab}",
            placeholder="Title — e.g. Cozy Desk Morning",
        )
        new_text = st.text_area(
            "Instruction",
            key=f"new_{tab}",
            placeholder="e.g. Place this product on a marble countertop with soft natural light",
            label_visibility="collapsed",
        )
        new_refs = st.file_uploader(
            "Reference image(s) — optional. Gemini will match their style/composition/lighting, not their product.",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key=f"newrefs_{tab}",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Add to saved list", key=f"add_{tab}", use_container_width=True):
                if new_text.strip():
                    store.add_instruction(data, tab, new_text.strip(), title=new_title.strip())
                    new_item = data[tab]["instructions"][-1]
                    attach_uploaded_references(tab, new_item["id"], new_refs)
                    st.rerun()
                else:
                    st.warning("Type an instruction first.")
        with c2:
            if st.button("⚡ Add & generate now", key=f"addgen_{tab}", use_container_width=True):
                if new_text.strip():
                    store.add_instruction(data, tab, new_text.strip(), title=new_title.strip())
                    new_item = data[tab]["instructions"][-1]
                    attach_uploaded_references(tab, new_item["id"], new_refs)
                    run_generation(tab, [new_item], source_image)
                    st.rerun()
                else:
                    st.warning("Type an instruction first.")

    st.divider()

    # --- saved instructions list ---
    selected_ids = []
    if not instructions:
        st.caption("No saved instructions yet — add one above.")
    else:
        st.caption(f"{len(instructions)} saved · 🕓 marks what you last generated on this tab")
        for item in instructions:
            iid, text = item["id"], item["text"]
            title = item.get("title", "")
            preview = title if title else (text if len(text) <= 72 else text[:72] + "…")
            ref_count = len(item.get("reference_images", []))

            with st.container(border=True):
                row = st.columns([0.06, 0.72, 0.22])
                checked = row[0].checkbox(
                    "Include", value=(iid in last_used), key=f"chk_{tab}_{iid}", label_visibility="collapsed"
                )
                if checked:
                    selected_ids.append(iid)

                marker = " 🕓" if iid in last_used else ""
                refs_note = f"  \n:gray[{ref_count} reference image(s)]" if ref_count else ""
                row[1].markdown(f"**{preview}**{marker}{refs_note}")

                if row[2].button("▶ Generate", key=f"gen1_{tab}_{iid}", use_container_width=True):
                    run_generation(tab, [item], source_image)
                    st.rerun()

                # Everything else (rename, edit the actual instruction, references, delete)
                # lives behind one disclosure — closed by default so a list of several saved
                # instructions reads as a clean list, not a wall of open edit forms.
                with st.expander("✏️ Edit instruction"):
                    new_title_val = st.text_input(
                        "Title", value=title, key=f"title_{tab}_{iid}",
                        placeholder="Untitled — give this prompt a name",
                    )
                    if new_title_val != title:
                        for inst in data[tab]["instructions"]:
                            if inst["id"] == iid:
                                inst["title"] = new_title_val
                        store.save(data)

                    edited = st.text_area(
                        "Instruction", value=text, key=f"edit_{tab}_{iid}", height=100,
                    )
                    if edited != text:
                        for inst in data[tab]["instructions"]:
                            if inst["id"] == iid:
                                inst["text"] = edited
                        store.save(data)
                        text = edited

                    st.write("")
                    st.caption(f"🖼️ Reference images ({ref_count}) — Gemini matches their style/composition/lighting, not their product.")
                    ref_list = item.get("reference_images", [])
                    if ref_list:
                        ref_cols = st.columns(min(4, len(ref_list)))
                        for ridx, rel_path in enumerate(ref_list):
                            with ref_cols[ridx % len(ref_cols)]:
                                abs_path = os.path.join(BASE_DIR, rel_path)
                                if os.path.exists(abs_path):
                                    st.image(abs_path, use_container_width=True)
                                else:
                                    st.caption("(file missing)")
                                if st.button("Remove", key=f"rmref_{tab}_{iid}_{ridx}", use_container_width=True):
                                    store.remove_reference_image(data, tab, iid, rel_path)
                                    st.rerun()
                    add_refs = st.file_uploader(
                        "Add reference image(s)",
                        type=["png", "jpg", "jpeg", "webp"],
                        accept_multiple_files=True,
                        key=f"addref_{tab}_{iid}",
                    )
                    if st.button("Add these", key=f"addrefbtn_{tab}_{iid}", disabled=not add_refs):
                        attach_uploaded_references(tab, iid, add_refs)
                        st.rerun()

                    st.divider()
                    if st.button("🗑️ Delete this instruction", key=f"del_{tab}_{iid}"):
                        store.delete_instruction(data, tab, iid)
                        st.rerun()

        st.write("")
        b1, b2 = st.columns(2)
        with b1:
            if st.button(
                f"▶ Generate selected ({len(selected_ids)})",
                key=f"gensel_{tab}",
                use_container_width=True,
                disabled=len(selected_ids) == 0,
            ):
                targets = [i for i in instructions if i["id"] in selected_ids]
                run_generation(tab, targets, source_image)
                st.rerun()
        with b2:
            if st.button(
                f"🚀 Generate All ({len(instructions)})",
                key=f"genall_{tab}",
                type="primary",
                use_container_width=True,
                disabled=len(instructions) == 0,
            ):
                run_generation(tab, instructions, source_image)
                st.rerun()

    # --- results gallery ---
    results = st.session_state.results.get(tab, [])
    if results:
        st.divider()
        st.write("**Results**")
        gallery_cols = st.columns(3)
        for idx, r in enumerate(results):
            with gallery_cols[idx % 3]:
                model_tag = MODEL_TO_SHORT_LABEL.get(r.get("model"))
                if r.get("title"):
                    st.markdown(f"**{r['title']}**")
                st.caption(r["text"])
                if model_tag:
                    st.markdown(f'<span class="tag-mono">{model_tag}</span>', unsafe_allow_html=True)
                if r["error"]:
                    st.error(r["error"])
                elif r["image_path"] and os.path.exists(r["image_path"]):
                    st.image(r["image_path"], use_container_width=True)
                    with open(r["image_path"], "rb") as f:
                        st.download_button(
                            "⬇️ Download",
                            data=f.read(),
                            file_name=os.path.basename(r["image_path"]),
                            mime="image/png",
                            key=f"dl_{tab}_{idx}_{r['id']}",
                            use_container_width=True,
                        )


# ---------------------------------------------------------------- sidebar (shared image)
st.title("📸 Madese Photo Studio")
st.markdown(
    '<p class="app-tagline">One product photo in, a shelf of styled variants out — for Amazon, Etsy and social.</p>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Product photo")
    uploaded_file = st.file_uploader(
        "Upload once, use it on any tab", type=["png", "jpg", "jpeg", "webp"]
    )
    source_image = None
    if uploaded_file is not None:
        try:
            source_image = Image.open(uploaded_file).convert("RGB")
            st.image(source_image, caption="Source photo", use_container_width=True)
        except Exception as e:
            st.error(f"Couldn't read that image: {e}")
    else:
        st.info("Upload a product photo to get started.")

    st.text_area(
        "What is this product? (optional, but recommended)",
        key="product_context",
        placeholder="e.g. A matte black ceramic coffee mug, 350ml, sold as a gift item for coffee lovers. Not a vase or a cup with a handle-less design.",
        help="Told to Gemini before every style instruction, so it stops guessing what the product is from the photo alone.",
        height=90,
    )

    if not os.environ.get("GEMINI_API_KEY"):
        st.warning("GEMINI_API_KEY not set. Add it to a .env file in this folder and restart the app.")

    st.divider()
    st.header("Model")
    selected_label = st.selectbox(
        "Used for the next Generate click",
        MODEL_LABELS,
        index=MODEL_LABELS.index(DEFAULT_MODEL_LABEL),
        key="model_select",
    )
    st.caption("Lite = fast drafts. Flash = balanced. Pro = best text/branding fidelity, costs more — good for final listing photos.")

# ---------------------------------------------------------------- tabs
tab_objs = st.tabs(TABS)
for tab_name, tab_obj in zip(TABS, tab_objs):
    with tab_obj:
        render_tab(tab_name)
