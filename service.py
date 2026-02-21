import os
import re
import uuid
import json
import base64
import shutil
import smtplib
import logging
import numpy as np
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from supabase import create_client
from groq import Groq
from deepface import DeepFace
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

supabase    = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_KEY)
groq_client = Groq(api_key=Config.GROQ_API_KEY)

IMAGE_EXTS = tuple(Config.ALLOWED_EXTENSIONS)

# ─────────────────────────────────────────────────────────────────────────────
# Disk layout:  UPLOAD_BASE_FOLDER / user_id / folder_name / filename.ext
# URL  layout:  /static/uploads   / user_id / folder_name / filename.ext
# Flask serves /static/... from the project's "static/" directory automatically.
# ─────────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def cosine_similarity(a: list, b: list) -> float:
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / d) if d else 0.0


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower().strip())
    return re.sub(r"[\s_-]+", "_", text)[:40].strip("_") or "folder"


def user_root(user_id: str) -> str:
    """Absolute disk path for a user's upload root. Created automatically."""
    p = os.path.join(Config.UPLOAD_BASE_FOLDER, user_id)
    os.makedirs(p, exist_ok=True)
    return p


# Alias so routes.py can import it
get_user_upload_root = user_root


def folder_disk(user_id: str, folder_name: str) -> str:
    """Absolute disk path for a person/folder. Created automatically."""
    p = os.path.join(user_root(user_id), folder_name)
    os.makedirs(p, exist_ok=True)
    return p


def make_url(user_id: str, folder_name: str, filename: str) -> str:
    """Browser URL served by Flask static handler."""
    return f"/static/uploads/{user_id}/{folder_name}/{filename}"


def list_images(folder_path: str) -> list[str]:
    """Sorted list of image filenames inside a disk folder."""
    try:
        return sorted(f for f in os.listdir(folder_path) if f.lower().endswith(IMAGE_EXTS))
    except FileNotFoundError:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# GROQ VISION FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

def _to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")


def groq_describe_for_folder(image_path: str) -> str:
    try:
        resp = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:{_mime(image_path)};base64,{_to_b64(image_path)}"}},
                {"type": "text",
                 "text": ("1-3 word snake_case folder name for image subject. "
                          "E.g.: beach_sunset, birthday_cake, dog_playing. "
                          "Reply ONLY with the slug.")},
            ]}],
            max_tokens=15, temperature=0.2,
        )
        raw  = resp.choices[0].message.content.strip().lower()
        slug = re.sub(r"[^\w]", "_", raw)[:40].strip("_")
        return slug or "uncategorised"
    except Exception as e:
        logger.warning(f"Groq vision: {e}")
        return "uncategorised"


def _find_or_create_scene_person(user_id: str, slug: str) -> dict:
    res = supabase.table("persons").select("*").eq("user_id", user_id).eq("folder_name", slug).execute()
    if res.data:
        return res.data[0]
    pid  = str(uuid.uuid4())
    row  = {"id": pid, "user_id": user_id, "name": slug.replace("_", " ").title(),
            "folder_name": slug, "embedding": None}
    supabase.table("persons").insert(row).execute()
    folder_disk(user_id, slug)
    return row


# ══════════════════════════════════════════════════════════════════════════════
# FACE RECOGNITION
# ══════════════════════════════════════════════════════════════════════════════

def extract_embeddings(image_path: str) -> list:
    try:
        return DeepFace.represent(img_path=image_path, model_name=Config.DEEPFACE_MODEL,
                                  detector_backend=Config.DEEPFACE_DETECTOR, enforce_detection=True)
    except Exception as e:
        logger.warning(f"DeepFace: {e}")
        return []


def find_matching_person(user_id: str, embedding: list) -> dict | None:
    persons = supabase.table("persons").select("*").eq("user_id", user_id).execute().data or []
    best, score, thresh = None, -1.0, 1.0 - Config.DEEPFACE_DISTANCE_THRESHOLD
    for p in persons:
        emb = p.get("embedding")
        if not emb:
            continue
        if isinstance(emb, dict):
            emb = emb.get("vector", [])
        if not emb:
            continue
        s = cosine_similarity(embedding, emb)
        if s > score:
            score, best = s, p
    return best if score >= thresh else None


def create_face_person(user_id: str, embedding: list) -> dict:
    pid  = str(uuid.uuid4())
    fname = f"person_{pid[:8]}"
    row  = {"id": pid, "user_id": user_id, "name": "Unknown",
            "folder_name": fname, "embedding": {"vector": embedding}}
    supabase.table("persons").insert(row).execute()
    folder_disk(user_id, fname)
    return row


# ══════════════════════════════════════════════════════════════════════════════
# UPLOAD PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def process_uploaded_image(user_id: str, image_path: str, filename: str) -> dict:
    result = {"filename": filename, "faces_detected": 0,
              "persons": [], "photo_id": None, "method": "deepface"}

    photo_id = str(uuid.uuid4())
    supabase.table("photos").insert({
        "id": photo_id, "user_id": user_id,
        "filename": filename, "filepath": filename,
    }).execute()
    result["photo_id"] = photo_id

    faces = extract_embeddings(image_path)
    result["faces_detected"] = len(faces)

    if faces:
        seen = set()
        for face in faces:
            emb = face.get("embedding", [])
            if not emb:
                continue
            person = find_matching_person(user_id, emb) or create_face_person(user_id, emb)
            if person["id"] in seen:
                continue
            seen.add(person["id"])
            _copy_to_folder(user_id, person["folder_name"], image_path, filename)
            _link(photo_id, person["id"])
            result["persons"].append({"name": person["name"], "folder": person["folder_name"], "id": person["id"]})
    else:
        result["method"] = "groq_vision"
        slug   = groq_describe_for_folder(image_path)
        person = _find_or_create_scene_person(user_id, slug)
        _copy_to_folder(user_id, person["folder_name"], image_path, filename)
        _link(photo_id, person["id"])
        result["persons"].append({"name": person["name"], "folder": person["folder_name"], "id": person["id"]})

    return result


def _copy_to_folder(user_id: str, folder_name: str, src: str, filename: str):
    dest = os.path.join(folder_disk(user_id, folder_name), filename)
    if not os.path.exists(dest):
        shutil.copy2(src, dest)


def _link(photo_id: str, person_id: str):
    supabase.table("photo_persons").insert({"photo_id": photo_id, "person_id": person_id}).execute()


# ══════════════════════════════════════════════════════════════════════════════
# PERSON / FOLDER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def get_all_persons(user_id: str) -> list[dict]:
    rows = supabase.table("persons").select("id,name,folder_name,created_at") \
             .eq("user_id", user_id).order("created_at").execute().data or []
    for p in rows:
        imgs = list_images(folder_disk(user_id, p["folder_name"]))
        p["photo_count"] = len(imgs)
        p["preview"]     = make_url(user_id, p["folder_name"], imgs[0]) if imgs else None
    return rows


def get_person_photos(person_id: str, user_id: str) -> list[dict]:
    res = supabase.table("persons").select("folder_name,name") \
            .eq("id", person_id).eq("user_id", user_id).execute()
    if not res.data:
        return []
    folder_name = res.data[0]["folder_name"]
    person_name = res.data[0]["name"]
    return [
        {"url": make_url(user_id, folder_name, f),
         "filename": f, "person_name": person_name,
         "person_id": person_id, "folder_name": folder_name}
        for f in list_images(folder_disk(user_id, folder_name))
    ]


def rename_person(person_id: str, user_id: str, new_name: str) -> bool:
    res = supabase.table("persons").update({"name": new_name}) \
            .eq("id", person_id).eq("user_id", user_id).execute()
    return bool(res.data)


def create_folder(user_id: str, display_name: str) -> dict:
    slug = slugify(display_name)
    if supabase.table("persons").select("id").eq("user_id", user_id).eq("folder_name", slug).execute().data:
        slug = f"{slug}_{uuid.uuid4().hex[:4]}"
    pid = str(uuid.uuid4())
    row = {"id": pid, "user_id": user_id, "name": display_name, "folder_name": slug, "embedding": None}
    supabase.table("persons").insert(row).execute()
    folder_disk(user_id, slug)
    return row


def delete_folder(person_id: str, user_id: str) -> bool:
    res = supabase.table("persons").select("folder_name") \
            .eq("id", person_id).eq("user_id", user_id).execute()
    if not res.data:
        return False
    fname = res.data[0]["folder_name"]

    # Find all photo_ids linked to this person, then delete photos + photo_persons
    pp_rows = supabase.table("photo_persons").select("photo_id") \
                .eq("person_id", person_id).execute().data or []
    photo_ids = [r["photo_id"] for r in pp_rows]

    # Delete photo_persons links first (FK constraint)
    supabase.table("photo_persons").delete().eq("person_id", person_id).execute()

    # Delete photos rows that now have no remaining person links
    for pid in photo_ids:
        remaining = supabase.table("photo_persons").select("id") \
                      .eq("photo_id", pid).execute().data or []
        if not remaining:
            supabase.table("photos").delete().eq("id", pid).execute()

    # Delete the person record
    supabase.table("persons").delete().eq("id", person_id).execute()

    # Remove disk folder
    shutil.rmtree(os.path.join(user_root(user_id), fname), ignore_errors=True)
    logger.info(f"Deleted folder {fname} and {len(photo_ids)} photo record(s)")
    return True


def delete_photo_from_folder(person_id: str, user_id: str, filename: str) -> bool:
    res = supabase.table("persons").select("folder_name") \
            .eq("id", person_id).eq("user_id", user_id).execute()
    if not res.data:
        return False
    fpath = os.path.join(folder_disk(user_id, res.data[0]["folder_name"]), filename)
    try:
        if os.path.isfile(fpath):
            os.remove(fpath)
    except Exception as e:
        logger.error(f"delete photo disk: {e}")
        return False

    # Remove photo_persons link for this person
    photos_rows = supabase.table("photos").select("id") \
                    .eq("user_id", user_id).eq("filename", filename).execute().data or []
    for ph in photos_rows:
        supabase.table("photo_persons").delete() \
            .eq("photo_id", ph["id"]).eq("person_id", person_id).execute()
        # If no more person links, delete the photos row too
        remaining = supabase.table("photo_persons").select("id") \
                      .eq("photo_id", ph["id"]).execute().data or []
        if not remaining:
            supabase.table("photos").delete().eq("id", ph["id"]).execute()

    return True


def move_photo_to_folder(user_id: str, src_person_id: str, dest_person_id: str,
                         filename: str, keep_in_source: bool = False) -> bool:
    src_res  = supabase.table("persons").select("folder_name").eq("id", src_person_id).eq("user_id", user_id).execute()
    dest_res = supabase.table("persons").select("folder_name").eq("id", dest_person_id).eq("user_id", user_id).execute()
    if not src_res.data or not dest_res.data:
        return False

    src_dir  = folder_disk(user_id, src_res.data[0]["folder_name"])
    dest_dir = folder_disk(user_id, dest_res.data[0]["folder_name"])
    src_file = os.path.join(src_dir, filename)
    dst_file = os.path.join(dest_dir, filename)

    if not os.path.isfile(src_file):
        return False

    shutil.copy2(src_file, dst_file)
    if not keep_in_source:
        os.remove(src_file)

    photos = supabase.table("photos").select("id").eq("user_id", user_id).eq("filename", filename).execute().data or []
    if photos:
        pid = photos[0]["id"]
        if not supabase.table("photo_persons").select("id").eq("photo_id", pid).eq("person_id", dest_person_id).execute().data:
            supabase.table("photo_persons").insert({"photo_id": pid, "person_id": dest_person_id}).execute()
        if not keep_in_source:
            supabase.table("photo_persons").delete().eq("photo_id", pid).eq("person_id", src_person_id).execute()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD STATS
# ══════════════════════════════════════════════════════════════════════════════

def get_dashboard_stats(user_id: str) -> dict:
    # Count persons live from DB (accurate after deletes)
    total_persons    = supabase.table("persons").select("id", count="exact") \
                         .eq("user_id", user_id).execute().count or 0
    total_deliveries = supabase.table("delivery_history").select("id", count="exact") \
                         .eq("user_id", user_id).execute().count or 0

    # Scan disk for accurate photo count + recent images (DB photos table may have orphans)
    persons = supabase.table("persons").select("id,folder_name,name") \
                .eq("user_id", user_id).execute().data or []

    all_imgs = []
    seen_filenames = set()   # deduplicate (same file copied to multiple folders)

    for p in persons:
        fdir = folder_disk(user_id, p["folder_name"])
        for fname in list_images(fdir):
            fpath = os.path.join(fdir, fname)
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                mtime = 0
            all_imgs.append({
                "filename":    fname,
                "url":         make_url(user_id, p["folder_name"], fname),
                "folder_name": p["folder_name"],
                "person_name": p["name"],
                "mtime":       mtime,
            })
            seen_filenames.add(fname)

    all_imgs.sort(key=lambda x: x["mtime"], reverse=True)

    # total_photos = unique files on disk (not DB count which can be stale)
    total_photos = len(seen_filenames)

    return {
        "total_photos":     total_photos,
        "total_persons":    total_persons,
        "total_deliveries": total_deliveries,
        "recent_photos":    all_imgs[:8],
    }


# ══════════════════════════════════════════════════════════════════════════════
# AI CHAT
# ══════════════════════════════════════════════════════════════════════════════

def _build_system_prompt(user_id: str) -> str:
    persons = get_all_persons(user_id)
    lines   = [f'  • "{p["name"]}"  folder={p["folder_name"]}  ({p["photo_count"]} photos)' for p in persons]
    block   = "\n".join(lines) if lines else "  (no folders yet)"
    return f"""You are Drishyamitra AI, a smart photo management assistant.

Current folders:
{block}

ACTIONS — put JSON on the LAST line of your reply:

{{"action":"show_photos","person_name":"<name>"}}
{{"action":"list_folders"}}
{{"action":"send_email","person_name":"<n>","recipient":"<email>"}}
{{"action":"rename_person","old_name":"<n>","new_name":"<new>"}}

Match names case-insensitively. For general questions answer directly without JSON. Be warm and concise.
"""


def chat_with_assistant(user_id: str, user_message: str, history: list) -> dict:
    messages = [{"role": "system", "content": _build_system_prompt(user_id)}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_message})

    try:
        resp  = groq_client.chat.completions.create(model=Config.GROQ_MODEL, messages=messages,
                                                     temperature=0.4, max_tokens=900)
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq: {e}")
        return {"reply": "Sorry, an error occurred.", "action": None, "photos": [], "folders": []}

    action_data, photos, folders, plain = None, [], [], reply
    try:
        last = reply.rfind("}")
        if last != -1:
            first = reply.rfind("{", 0, last + 1)
            if first != -1:
                action_data = json.loads(reply[first:last + 1])
                plain       = reply[:first].strip() or reply[last + 1:].strip()
                act = action_data.get("action")

                if act == "show_photos":
                    person = _find_person_by_name(user_id, action_data.get("person_name", ""))
                    if person:
                        photos = get_person_photos(person["id"], user_id)
                        plain  = plain or f"Here are the photos of **{person['name']}**:"
                    else:
                        plain = "Couldn't find that person. Check People & Folders."

                elif act == "list_folders":
                    persons = get_all_persons(user_id)
                    folders = [{"id": p["id"], "name": p["name"], "photo_count": p["photo_count"],
                                "preview": p.get("preview"), "folder_name": p["folder_name"]} for p in persons]
                    plain   = plain or f"You have **{len(folders)}** folder(s):"

                elif act == "send_email":
                    person = _find_person_by_name(user_id, action_data.get("person_name", ""))
                    recip  = action_data.get("recipient", "")
                    if person and recip:
                        r     = send_photos_by_email(user_id, person["id"], recip)
                        plain = (f"✅ Sent **{r['photos_sent']}** photo(s) to **{recip}**!"
                                 if r["success"] else f"❌ Failed: {r.get('error')}")
                    else:
                        plain = "Provide a valid person name and recipient email."

                elif act == "rename_person":
                    person = _find_person_by_name(user_id, action_data.get("old_name", ""))
                    new    = action_data.get("new_name", "")
                    if person and new:
                        rename_person(person["id"], user_id, new)
                        plain = f"✅ Renamed to **{new}**!"
                    else:
                        plain = "Could not find that person."
    except Exception:
        plain = reply

    return {"reply": plain or reply, "action": action_data, "photos": photos, "folders": folders}


def _find_person_by_name(user_id: str, name: str) -> dict | None:
    if not name:
        return None
    data = supabase.table("persons").select("*").eq("user_id", user_id) \
             .ilike("name", f"%{name}%").execute().data or []
    return data[0] if data else None


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL
# ══════════════════════════════════════════════════════════════════════════════

def send_photos_by_email(user_id: str, person_id: str,
                         recipient_email: str, custom_message: str = "") -> dict:
    res = supabase.table("persons").select("name,folder_name").eq("id", person_id).execute()
    if not res.data:
        return {"success": False, "error": "Person not found"}
    person = res.data[0]
    fdir   = folder_disk(user_id, person["folder_name"])
    files  = [os.path.join(fdir, f) for f in list_images(fdir)]
    if not files:
        return {"success": False, "error": "No photos found"}

    msg = MIMEMultipart()
    msg["From"], msg["To"] = Config.GMAIL_EMAIL, recipient_email
    msg["Subject"] = f"Photos of {person['name']} – Drishyamitra"
    msg.attach(MIMEText(custom_message or
        f"Hi,\n\nAttached: {len(files)} photo(s) of {person['name']}.\n\nDrishyamitra", "plain"))

    attached = 0
    for fp in files[:10]:
        try:
            with open(fp, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(fp)}")
            msg.attach(part); attached += 1
        except Exception as e:
            logger.warning(f"attach: {e}")

    try:
        with smtplib.SMTP(Config.GMAIL_SMTP_HOST, Config.GMAIL_SMTP_PORT) as s:
            s.ehlo(); s.starttls()
            s.login(Config.GMAIL_EMAIL, Config.GMAIL_APP_PASSWORD)
            s.sendmail(Config.GMAIL_EMAIL, recipient_email, msg.as_string())
    except Exception as e:
        _log_delivery(user_id, person_id, recipient_email, attached, "failed", str(e))
        return {"success": False, "error": str(e)}

    _log_delivery(user_id, person_id, recipient_email, attached, "sent", "")
    return {"success": True, "photos_sent": attached}


def _log_delivery(user_id, person_id, recipient, count, status, message):
    supabase.table("delivery_history").insert({
        "user_id": user_id, "person_id": person_id,
        "recipient_email": recipient, "photo_count": count,
        "status": status, "message": message,
    }).execute()


def get_delivery_history(user_id: str) -> list:
    return supabase.table("delivery_history").select("*, persons(name,folder_name)") \
             .eq("user_id", user_id).order("delivered_at", desc=True).execute().data or []