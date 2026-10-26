import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Security ──────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY', 'routecraft-dev-secret-2026')

    # ── MySQL ─────────────────────────────────────────────────
    MYSQL_HOST     = os.environ.get('MYSQL_HOST',     'localhost')
    MYSQL_USER     = os.environ.get('MYSQL_USER',     'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB       = os.environ.get('MYSQL_DB',       'travel_planner')
    MYSQL_CURSORCLASS = 'DictCursor'

    # ── File Uploads ──────────────────────────────────────────
    UPLOAD_FOLDER      = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024   # 5 MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # ── External APIs ─────────────────────────────────────────
    OPENWEATHER_API_KEY = os.environ.get('OPENWEATHER_API_KEY', '')
    CURRENCY_API_KEY    = os.environ.get('CURRENCY_API_KEY',    '')

    # ── Mail ──────────────────────────────────────────────────
    MAIL_SERVER         = os.environ.get('MAIL_SERVER',   'smtp.gmail.com')
    MAIL_PORT           = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS        = True
    MAIL_USERNAME       = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD       = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')

    # ── Session ───────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400   # 24 hours


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


config = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'default':     DevelopmentConfig,
}
