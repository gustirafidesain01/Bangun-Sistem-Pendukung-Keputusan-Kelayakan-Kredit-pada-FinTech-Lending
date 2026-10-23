import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "ganti-dengan-kunci-rahasia-anda")

    # --- Koneksi Database ---
    # Default: MySQL via XAMPP (user root, tanpa password, port 3306)
    # Ganti nilai di file .env jika konfigurasi XAMPP kamu berbeda.
    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = os.environ.get("DB_PORT", "3306")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "credit_scoring")

    # Mode fallback: kalau USE_SQLITE=1 di .env, pakai SQLite (tanpa perlu XAMPP)
    # Berguna untuk uji coba cepat sebelum menyambungkan ke MySQL.
    USE_SQLITE = os.environ.get("USE_SQLITE", "0") == "1"

    if USE_SQLITE:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'credit_scoring.db')}"
    else:
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
