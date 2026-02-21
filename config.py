import os
class Config:
    SECRET_KEY = "drishyamitra-secret-key-change-in-production-2024"
    DEBUG = True
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB max upload
    SUPABASE_URL =""
    SUPABASE_KEY =""         # anon/public key
    SUPABASE_SERVICE_KEY = ""  # service role key
    GROQ_API_KEY = ""
    GROQ_MODEL = "llama-3.3-70b-versatile"
    GMAIL_EMAIL = ""
    GMAIL_APP_PASSWORD = ""   # Gmail App Password
    GMAIL_SMTP_HOST = ""
    GMAIL_SMTP_PORT = 587
    UPLOAD_BASE_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
    DEEPFACE_MODEL = "Facenet512"
    DEEPFACE_DETECTOR = "retinaface"
    DEEPFACE_DISTANCE_THRESHOLD = 0.40  
    TEAM = [
        {
            "name": "V. BARADWAJA",
            "role": "Team Lead & AI Engineer",
            "avatar": "VB",
            "bio": "Specializes in computer vision and deep learning. Led the DeepFace integration and face recognition pipeline.",
            "skills": ["DeepFace", "Python", "Flask", "Computer Vision"]
        },
        {
            "name": "R. GEETHA KRISHNA",
            "role": "Full-Stack Developer",
            "avatar": "RGK",
            "bio": "Built the Flask backend architecture and Supabase database schema. Expert in API development.",
            "skills": ["Flask", "Supabase", "REST APIs", "SQL"]
        },
        {
            "name": "S. SRI LAKSHMI",
            "role": "AI & NLP Engineer",
            "avatar": "SSL",
            "bio": "Designed the Groq-powered AI Chat Assistant with natural language query processing for photo management.",
            "skills": ["Groq API", "NLP", "LLM", "Prompt Engineering"]
        },
        {
            "name": "M. VISHNAVI",
            "role": "UI/UX & Frontend Developer",
            "avatar": "MV",
            "bio": "Crafted the complete UI/UX design, landing page, and responsive templates for the entire application.",
            "skills": ["HTML/CSS", "JavaScript", "UI Design", "Jinja2"]
        }
    ]
    PROJECT_NAME = "Drishyamitra"
    PROJECT_TAGLINE = "AI-Powered Photo Management System"
    PROJECT_VERSION = "1.0.0"
    PROJECT_YEAR = "2024"