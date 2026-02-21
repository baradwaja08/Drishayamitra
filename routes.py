import os
import uuid
from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from werkzeug.utils import secure_filename
from config import Config
from service import (
    allowed_file, process_uploaded_image,
    get_all_persons, get_person_photos, rename_person,
    create_folder, delete_folder, delete_photo_from_folder, move_photo_to_folder,
    send_photos_by_email, get_delivery_history, get_dashboard_stats,
    chat_with_assistant, get_user_upload_root,
)

main_bp = Blueprint("main", __name__)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in.", "warning")
            return redirect(url_for("auth.auth_page", tab="login"))
        return f(*args, **kwargs)
    return wrapper


# ── Landing ───────────────────────────────────────────────────────────────────

@main_bp.route("/")
def landing():
    return render_template("landing.html", team=Config.TEAM, config=Config)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@main_bp.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    return render_template("dashboard.html",
                           stats=get_dashboard_stats(uid),
                           persons=get_all_persons(uid),
                           user_name=session.get("user_name"))


# ── Upload ────────────────────────────────────────────────────────────────────

@main_bp.route("/upload", methods=["POST"])
@login_required
def upload_photo():
    uid   = session["user_id"]
    files = request.files.getlist("photos")
    count, faces = 0, 0
    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename):
            flash(f"Skipped: {file.filename}", "warning")
            continue
        safe = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        temp = os.path.join(get_user_upload_root(uid), safe)
        file.save(temp)
        r = process_uploaded_image(uid, temp, safe)
        count += 1; faces += r["faces_detected"]

    if count:
        flash(f"✅ Uploaded {count} photo(s) · {faces} face(s) detected.", "success")
    else:
        flash("No valid files uploaded.", "error")
    return redirect(url_for("main.dashboard"))


# ── Persons / Folders ─────────────────────────────────────────────────────────

@main_bp.route("/persons")
@login_required
def persons_page():
    uid = session["user_id"]
    return render_template("dashboard.html",
                           view="persons",
                           persons=get_all_persons(uid),
                           stats=get_dashboard_stats(uid),
                           user_name=session.get("user_name"))


@main_bp.route("/person/<person_id>/photos")
@login_required
def person_photos(person_id: str):
    uid     = session["user_id"]
    persons = get_all_persons(uid)
    person  = next((p for p in persons if p["id"] == person_id), None)
    photos  = get_person_photos(person_id, uid)
    return render_template("dashboard.html",
                           view="person_photos",
                           person=person,
                           photos=photos,
                           persons=persons,
                           stats=get_dashboard_stats(uid),
                           user_name=session.get("user_name"))


@main_bp.route("/person/<person_id>/rename", methods=["POST"])
@login_required
def rename_person_route(person_id: str):
    uid  = session["user_id"]
    name = request.form.get("name", "").strip()
    if name:
        rename_person(person_id, uid, name)
        flash(f"Renamed to '{name}'.", "success")
    else:
        flash("Name cannot be empty.", "error")
    return redirect(request.referrer or url_for("main.persons_page"))


@main_bp.route("/folder/create", methods=["POST"])
@login_required
def create_folder_route():
    uid  = session["user_id"]
    name = request.form.get("folder_name", "").strip()
    if name:
        create_folder(uid, name)
        flash(f"Folder '{name}' created.", "success")
    else:
        flash("Folder name cannot be empty.", "error")
    return redirect(url_for("main.persons_page"))


@main_bp.route("/person/<person_id>/delete", methods=["POST"])
@login_required
def delete_folder_route(person_id: str):
    uid = session["user_id"]
    if delete_folder(person_id, uid):
        flash("Folder deleted.", "success")
    else:
        flash("Could not delete folder.", "error")
    return redirect(url_for("main.persons_page"))


@main_bp.route("/person/<person_id>/photo/delete", methods=["POST"])
@login_required
def delete_photo_route(person_id: str):
    uid      = session["user_id"]
    filename = request.form.get("filename", "").strip()
    if filename and delete_photo_from_folder(person_id, uid, filename):
        flash("Photo deleted.", "success")
    else:
        flash("Could not delete photo.", "error")
    return redirect(url_for("main.person_photos", person_id=person_id))


@main_bp.route("/person/<person_id>/photo/move", methods=["POST"])
@login_required
def move_photo_route(person_id: str):
    uid       = session["user_id"]
    filename  = request.form.get("filename", "").strip()
    dest_id   = request.form.get("dest_person_id", "").strip()
    keep      = request.form.get("keep_copy") == "1"
    if filename and dest_id:
        if move_photo_to_folder(uid, person_id, dest_id, filename, keep_in_source=keep):
            flash("Photo moved.", "success")
        else:
            flash("Could not move photo.", "error")
    return redirect(url_for("main.person_photos", person_id=person_id))


# ── Email ─────────────────────────────────────────────────────────────────────

@main_bp.route("/send-email", methods=["POST"])
@login_required
def send_email_route():
    uid       = session["user_id"]
    person_id = request.form.get("person_id")
    recipient = request.form.get("recipient_email", "").strip()
    msg       = request.form.get("message", "").strip()
    if not person_id or not recipient:
        flash("Person and recipient email required.", "error")
        return redirect(request.referrer or url_for("main.dashboard"))
    r = send_photos_by_email(uid, person_id, recipient, msg)
    if r["success"]:
        flash(f"✅ Sent {r['photos_sent']} photo(s) to {recipient}!", "success")
    else:
        flash(f"❌ Failed: {r.get('error')}", "error")
    return redirect(request.referrer or url_for("main.history"))


# ── History ───────────────────────────────────────────────────────────────────

@main_bp.route("/history")
@login_required
def history():
    uid = session["user_id"]
    return render_template("history.html",
                           deliveries=get_delivery_history(uid),
                           persons=get_all_persons(uid),
                           user_name=session.get("user_name"))


# ── AI Chat API ───────────────────────────────────────────────────────────────

@main_bp.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    uid  = session["user_id"]
    data = request.get_json(force=True)
    msg  = data.get("message", "").strip()
    if not msg:
        return jsonify({"error": "empty"}), 400
    return jsonify(chat_with_assistant(uid, msg, data.get("history", [])))


@main_bp.route("/api/persons")
@login_required
def api_persons():
    return jsonify(get_all_persons(session["user_id"]))


@main_bp.route("/api/person/<person_id>/photos")
@login_required
def api_person_photos(person_id: str):
    return jsonify(get_person_photos(person_id, session["user_id"]))