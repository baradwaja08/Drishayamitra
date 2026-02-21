import uuid
import secrets
import hashlib
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from supabase import create_client
from config import Config

auth_bp = Blueprint("auth", __name__)
supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_KEY)


# ── Helpers ───────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def send_email_util(to: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["From"] = Config.GMAIL_EMAIL
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP(Config.GMAIL_SMTP_HOST, Config.GMAIL_SMTP_PORT) as s:
        s.ehlo()
        s.starttls()
        s.login(Config.GMAIL_EMAIL, Config.GMAIL_APP_PASSWORD)
        s.sendmail(Config.GMAIL_EMAIL, to, msg.as_string())


# ══════════════════════════════════════════════════════════════════════════════
# AUTH PAGE (login + signup on same page via tab)
# ══════════════════════════════════════════════════════════════════════════════

@auth_bp.route("/auth", methods=["GET"])
def auth_page():
    if "user_id" in session:
        return redirect(url_for("main.dashboard"))
    return render_template("auth.html", tab=request.args.get("tab", "login"))


# ── SIGN UP ───────────────────────────────────────────────────────────────────

@auth_bp.route("/signup", methods=["POST"])
def signup():
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not all([full_name, email, password, confirm]):
        flash("All fields are required.", "error")
        return redirect(url_for("auth.auth_page", tab="signup"))

    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("auth.auth_page", tab="signup"))

    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("auth.auth_page", tab="signup"))

    # check duplicate
    existing = (
        supabase.table("users").select("id").eq("email", email).execute().data
    )
    if existing:
        flash("An account with this email already exists.", "error")
        return redirect(url_for("auth.auth_page", tab="signup"))

    user_id = str(uuid.uuid4())
    supabase.table("users").insert(
        {
            "id": user_id,
            "email": email,
            "password_hash": hash_password(password),
            "full_name": full_name,
        }
    ).execute()

    # welcome email
    try:
        send_email_util(
            to=email,
            subject="Welcome to Drishyamitra 🎉",
            html_body=f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:30px;
                        background:#f9f9f9;border-radius:12px;">
              <h1 style="color:#6c63ff;">Welcome to Drishyamitra!</h1>
              <p>Hi <strong>{full_name}</strong>,</p>
              <p>Your account has been created successfully.
                 Start uploading photos and let our AI organize them for you!</p>
              <a href="{url_for('auth.auth_page', _external=True)}"
                 style="display:inline-block;padding:12px 24px;background:#6c63ff;
                        color:white;border-radius:8px;text-decoration:none;margin-top:16px;">
                Log In Now
              </a>
              <p style="margin-top:24px;color:#888;">— The Drishyamitra Team</p>
            </div>""",
        )
    except Exception:
        pass  # don't block signup if email fails

    flash("Account created! Please log in.", "success")
    return redirect(url_for("auth.auth_page", tab="login"))


# ── LOGIN ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Email and password are required.", "error")
        return redirect(url_for("auth.auth_page", tab="login"))

    res = (
        supabase.table("users")
        .select("*")
        .eq("email", email)
        .eq("password_hash", hash_password(password))
        .execute()
    )
    user = res.data[0] if res.data else None

    if not user:
        flash("Invalid email or password.", "error")
        return redirect(url_for("auth.auth_page", tab="login"))

    session.permanent = True
    session["user_id"] = user["id"]
    session["user_name"] = user["full_name"]
    session["user_email"] = user["email"]
    return redirect(url_for("main.dashboard"))


# ── FORGOT PASSWORD ───────────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("auth.html", tab="forgot")

    email = request.form.get("email", "").strip().lower()
    if not email:
        flash("Please enter your email address.", "error")
        return redirect(url_for("auth.forgot_password"))

    user_res = supabase.table("users").select("id, full_name").eq("email", email).execute()
    if not user_res.data:
        # Don't reveal whether email exists
        flash("If that email is registered, a reset link has been sent.", "info")
        return redirect(url_for("auth.auth_page", tab="login"))

    user = user_res.data[0]
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()

    supabase.table("reset_tokens").insert(
        {
            "user_id": user["id"],
            "token": token,
            "expires_at": expires_at,
        }
    ).execute()

    reset_link = url_for("auth.reset_password", token=token, _external=True)
    try:
        send_email_util(
            to=email,
            subject="Drishyamitra – Password Reset Request",
            html_body=f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:30px;
                        background:#f9f9f9;border-radius:12px;">
              <h2 style="color:#6c63ff;">Password Reset Request</h2>
              <p>Hi <strong>{user['full_name']}</strong>,</p>
              <p>Click the button below to reset your password.
                 This link expires in <strong>1 hour</strong>.</p>
              <a href="{reset_link}"
                 style="display:inline-block;padding:12px 24px;background:#e74c3c;
                        color:white;border-radius:8px;text-decoration:none;margin-top:16px;">
                Reset Password
              </a>
              <p style="margin-top:16px;color:#888;font-size:13px;">
                If you didn't request this, please ignore this email.
              </p>
              <p style="color:#888;">— The Drishyamitra Team</p>
            </div>""",
        )
    except Exception as e:
        flash("Could not send reset email. Check server email config.", "error")
        return redirect(url_for("auth.forgot_password"))

    flash("If that email is registered, a reset link has been sent.", "info")
    return redirect(url_for("auth.auth_page", tab="login"))


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    # Validate token
    res = (
        supabase.table("reset_tokens")
        .select("*")
        .eq("token", token)
        .eq("used", False)
        .execute()
    )
    token_row = res.data[0] if res.data else None

    if not token_row:
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("auth.auth_page", tab="login"))

    # check expiry
    expires_at = datetime.fromisoformat(token_row["expires_at"].replace("Z", ""))
    if datetime.utcnow() > expires_at:
        flash("This reset link has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "GET":
        return render_template("auth.html", tab="reset", token=token)

    new_password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not new_password or len(new_password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("auth.reset_password", token=token))

    if new_password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("auth.reset_password", token=token))

    # update password
    supabase.table("users").update(
        {"password_hash": hash_password(new_password)}
    ).eq("id", token_row["user_id"]).execute()

    # mark token used
    supabase.table("reset_tokens").update({"used": True}).eq("token", token).execute()

    flash("Password updated successfully. Please log in.", "success")
    return redirect(url_for("auth.auth_page", tab="login"))


# ── LOGOUT ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.auth_page", tab="login"))