"""
Reads/writes prompts.json — the persistent library of instructions per tab,
plus each tab's "last_used" instruction ids.

Schema:
{
  "<Tab Name>": {
    "instructions": [{"id": "<8-char hex>", "text": "<instruction text>"}, ...],
    "last_used": ["<id>", ...]   # ids from the most recent Generate click on this tab
  },
  ...
}
"""
import json
import os
import uuid
from threading import Lock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_PATH = os.path.join(BASE_DIR, "prompts.json")
REFERENCE_IMAGES_DIR = os.path.join(BASE_DIR, "reference_images")
_lock = Lock()

TABS = ["Lifestyle Shots", "Clean Listing Photos", "Social/Reel Thumbnails"]

# Sensible starter examples so the app isn't blank on first run / if prompts.json
# ever goes missing or gets corrupted. Each entry is (title, instruction text).
DEFAULT_PROMPTS = {
    "Lifestyle Shots": [
        ("Cozy Desk Morning", "Place this product on a rustic wooden desk next to a steaming coffee mug and an open notebook, soft warm morning window light, shallow depth of field."),
        ("Held Outdoors", "Show this product being held in someone's hand outdoors in natural daylight, with a softly blurred park or garden background."),
        ("Shelf String Lights", "Set this product on a cozy living room shelf with warm string lights and a small plant nearby, evening ambience."),
    ],
    "Clean Listing Photos": [
        ("Pure White Isolated", "Isolate this product on a pure white seamless background, bright even studio lighting, no visible shadows, straight-on e-commerce catalog style."),
        ("Grey Background Shadow", "Place this product on a plain light-grey background with a soft, subtle drop shadow beneath it, centered in frame."),
        ("3/4 Angle White", "Show this product on a white background photographed at a 3/4 angle with gentle studio reflections, high resolution product photography."),
    ],
    "Social/Reel Thumbnails": [
        ("Bold Gradient Thumbnail", "Create a bold, high-contrast thumbnail of this product with a vibrant colorful gradient background, eye-catching style for Instagram Reels."),
        ("Neon Rim Dark", "Close-up dramatic shot of this product with colorful neon rim lighting against a dark background, cinematic mood."),
        ("Colorful Flat-Lay", "Playful flat-lay composition of this product surrounded by matching colorful props on a bright, saturated background."),
    ],
}


def _new_instruction(text: str, title: str = "") -> dict:
    return {"id": uuid.uuid4().hex[:8], "title": title, "text": text, "reference_images": []}


def safe_folder_name(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).strip("_")


def _default_state() -> dict:
    return {
        tab: {
            "instructions": [_new_instruction(text, title) for title, text in DEFAULT_PROMPTS[tab]],
            "last_used": [],
        }
        for tab in TABS
    }


def _save_unlocked(data: dict) -> None:
    tmp_path = PROMPTS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, PROMPTS_PATH)  # atomic on both POSIX and Windows


def save(data: dict) -> None:
    with _lock:
        _save_unlocked(data)


def load() -> dict:
    """Load prompts.json, creating it with defaults if missing/corrupt,
    and backfilling any tabs a schema upgrade might have added."""
    with _lock:
        if not os.path.exists(PROMPTS_PATH):
            data = _default_state()
            _save_unlocked(data)
            return data
        try:
            with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = _default_state()
            _save_unlocked(data)
            return data

        changed = False
        for tab in TABS:
            if tab not in data or not isinstance(data.get(tab), dict):
                data[tab] = {
                    "instructions": [_new_instruction(text, title) for title, text in DEFAULT_PROMPTS[tab]],
                    "last_used": [],
                }
                changed = True
            else:
                data[tab].setdefault("instructions", [])
                data[tab].setdefault("last_used", [])
                for inst in data[tab]["instructions"]:
                    if "reference_images" not in inst:
                        inst["reference_images"] = []
                        changed = True
                    if "title" not in inst:
                        inst["title"] = ""
                        changed = True
        if changed:
            _save_unlocked(data)
        return data


def add_instruction(data: dict, tab: str, text: str, title: str = "") -> dict:
    text = text.strip()
    if text:
        data[tab]["instructions"].append(_new_instruction(text, title.strip()))
        save(data)
    return data


def delete_instruction(data: dict, tab: str, instruction_id: str) -> dict:
    data[tab]["instructions"] = [i for i in data[tab]["instructions"] if i["id"] != instruction_id]
    data[tab]["last_used"] = [i for i in data[tab]["last_used"] if i != instruction_id]
    save(data)
    return data


def set_last_used(data: dict, tab: str, instruction_ids: list) -> dict:
    data[tab]["last_used"] = list(instruction_ids)
    save(data)
    return data


def add_reference_image(data: dict, tab: str, instruction_id: str, image) -> str:
    """Save a reference image (PIL.Image) to disk for one instruction, record its
    path in prompts.json, and return the relative path that was stored."""
    folder = os.path.join(REFERENCE_IMAGES_DIR, safe_folder_name(tab), instruction_id)
    os.makedirs(folder, exist_ok=True)
    filename = f"{uuid.uuid4().hex[:8]}.png"
    abs_path = os.path.join(folder, filename)
    image.save(abs_path)
    rel_path = os.path.relpath(abs_path, BASE_DIR).replace("\\", "/")
    for inst in data[tab]["instructions"]:
        if inst["id"] == instruction_id:
            inst.setdefault("reference_images", []).append(rel_path)
    save(data)
    return rel_path


def remove_reference_image(data: dict, tab: str, instruction_id: str, rel_path: str) -> None:
    for inst in data[tab]["instructions"]:
        if inst["id"] == instruction_id:
            inst["reference_images"] = [p for p in inst.get("reference_images", []) if p != rel_path]
    save(data)
    abs_path = os.path.join(BASE_DIR, rel_path)
    try:
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except OSError:
        pass
