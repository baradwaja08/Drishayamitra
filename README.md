# 👁️ Drishyamitra – AI-Powered Photo Management System

> **"Drishyamitra" (दृश्यमित्र)** means _"Visual Companion"_ in Sanskrit.  
> Upload photos once. AI organizes everything — automatically.

---

## 🚀 What It Does

Drishyamitra detects faces in every uploaded photo and automatically:

- Creates a dedicated folder for each **unique person** detected
- Routes photos of the **same person** into their existing folder
- Saves photos of **multiple people** into **all** their respective folders
- Lets you **find, rename, and email** photos through an AI chat assistant

Think of it as **Google Photos** — but built with Flask + Supabase on your own server.

---

## 🏗️ Architecture

```
your_project/
│
├── app.py          → Flask app factory & entry point
├── config.py       → ALL configuration (keys, credentials, team info)
├── service.py      → Core AI logic: face recognition, folder management, email, chat
├── auth.py         → Auth blueprint: login, signup, forgot/reset password
├── routes.py       → Main blueprint: dashboard, upload, history, chat API
├── requirements.txt
│
├── static/
│   └── style.css   → Single CSS file for all pages
│
└── templates/
    ├── landing.html   → Public homepage with features, team, use cases
    ├── auth.html      → Login / Sign Up / Forgot / Reset Password
    ├── dashboard.html → App dashboard: upload, folders, gallery, AI chat
    └── history.html   → Delivery history with re-send per record
```

---

## 🗄️ Supabase Schema (copy-paste into SQL Editor)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT DEFAULT 'Unknown',
    folder_name TEXT NOT NULL,
    embedding JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE photos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE photo_persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    photo_id UUID REFERENCES photos(id) ON DELETE CASCADE,
    person_id UUID REFERENCES persons(id) ON DELETE CASCADE
);

CREATE TABLE delivery_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    person_id UUID REFERENCES persons(id),
    recipient_email TEXT NOT NULL,
    photo_count INTEGER,
    status TEXT DEFAULT 'sent',
    message TEXT,
    delivered_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN DEFAULT FALSE
);
```

---

## ⚙️ How Face Detection & Folders Work

```
User uploads image.jpg
         ↓
DeepFace (Facenet512 + RetinaFace) detects faces
         ↓
For each face detected:
    → Extract 512-dimension embedding vector
    → Compare against all stored persons (cosine similarity)
    → Score ≥ threshold?
         YES → Existing person matched → copy photo to that folder
         NO  → New person → create folder "person_<uuid8>" → save embedding
         ↓
photo_persons table links photo ↔ all matched persons
         ↓
Result: photo of 3 people → saved in 3 different folders simultaneously
```

---

## 🧪 Prerequisites

| Tool   | Minimum Version |
| ------ | --------------- |
| Python | 3.10+           |
| pip    | 23+             |

---

## 🛠️ Setup & Installation

### 1. Clone & create virtual environment

```bash
git clone <your-repo-url>
cd your_project
python -m venv venv

# Activate:
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

> First run will auto-download DeepFace models (~500MB). Keep internet on.

### 3. Configure `config.py`

Open `config.py` and fill in:

```python
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "YOUR_ANON_KEY"
SUPABASE_SERVICE_KEY = "YOUR_SERVICE_KEY"
GROQ_API_KEY = "YOUR_GROQ_KEY"
GMAIL_EMAIL = "your@gmail.com"
GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"   # 16-char App Password
```

### 4. Set up Supabase

- Go to [supabase.com](https://supabase.com) → New Project
- Open **SQL Editor** → paste the schema from above → Run

### 5. Run the server

```bash
python app.py
```

Visit → http://localhost:5000

---

## 🔑 Getting API Keys

### Groq API

1. Sign up at https://console.groq.com
2. Go to API Keys → Create new key
3. Paste into `GROQ_API_KEY` in config.py

### Gmail App Password

1. Google Account → Security → 2-Step Verification (enable it)
2. Search "App Passwords" → Create for Mail
3. Copy 16-char password → paste into `GMAIL_APP_PASSWORD`

### Supabase

1. Create project at https://supabase.com
2. Settings → API → copy `Project URL` and `anon` + `service_role` keys

---

## 📱 Pages

| URL                       | Page             | Description                                    |
| ------------------------- | ---------------- | ---------------------------------------------- |
| `/`                       | Landing          | Public homepage with features, team, use cases |
| `/auth?tab=login`         | Login            | Email + password authentication                |
| `/auth?tab=signup`        | Sign Up          | New account registration                       |
| `/forgot-password`        | Forgot Password  | Email reset link                               |
| `/reset-password/<token>` | Reset Password   | Set new password via token                     |
| `/dashboard`              | Dashboard        | Upload, view folders, stats                    |
| `/persons`                | People & Folders | All detected person folders                    |
| `/person/<id>/photos`     | Person Photos    | All photos in a folder                         |
| `/history`                | Delivery History | All emails sent, with re-send button           |
| `/api/chat`               | AI Chat API      | POST JSON, returns AI reply + photos           |

---

## 💬 AI Chat Commands

| You say                                 | What happens                             |
| --------------------------------------- | ---------------------------------------- |
| `Show photos of Mom`                    | Displays all photos in Mom's folder      |
| `Show me pictures of Priya`             | Finds Priya's folder and displays photos |
| `Send Dad's photos to john@example.com` | Emails all photos in Dad's folder        |
| `Rename Unknown to Grandma`             | Renames the person folder                |
| `How many people have been detected?`   | Returns count from your folders          |

---

## 🔒 Security

- Passwords hashed with SHA-256 before storage
- Password reset tokens expire in 1 hour and are single-use
- All routes protected by session-based login_required decorator
- User data is isolated: each user only sees their own folders/photos
- Upload directory organized by user_id for strict separation

---

## 🧑‍💻 Team

| Name              | Role                       |
| ----------------- | -------------------------- |
| V. BARADWAJA      | Team Lead & AI Engineer    |
| R. GEETHA KRISHNA | Full-Stack Developer       |
| S. SRI LAKSHMI    | AI & NLP Engineer          |
| M. VISHNAVI       | UI/UX & Frontend Developer |

---

## 📦 Tech Stack

| Layer            | Technology                         |
| ---------------- | ---------------------------------- |
| Backend          | Flask 3.0                          |
| Database         | Supabase (PostgreSQL)              |
| Face Recognition | DeepFace (Facenet512 + RetinaFace) |
| AI Chat          | Groq API (Llama 3.3 70B)           |
| Email            | Gmail SMTP                         |
| Frontend         | Jinja2 + Vanilla JS + CSS          |

---

## 🐞 Troubleshooting

**DeepFace first-run is slow?**  
Models are ~500MB and download automatically. Wait for completion on first upload.

**No faces detected?**  
Ensure photo is well-lit, face is clearly visible, and not too small. MTCNN/RetinaFace needs ~50px face size minimum.

**Email not sending?**  
Verify Gmail App Password (not your main password). Make sure 2-Step Verification is enabled.

**Supabase connection error?**  
Check your `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in config.py.

---

© 2026 Drishyamitra — Built with ❤️ by the Team
