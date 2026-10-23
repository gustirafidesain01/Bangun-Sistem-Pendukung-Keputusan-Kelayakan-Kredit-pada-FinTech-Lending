from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

HAPUS_RETENSI_HARI = 30  # masa tempat sampah sebelum data hilang permanen


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nama_lengkap = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="analis")  # 'analis' atau 'admin'
    aktif = db.Column(db.Boolean, default=True)
    dibuat_pada = db.Column(db.DateTime, default=datetime.utcnow)

    pengajuan_dibuat = db.relationship(
        "Pengajuan", backref="dibuat_oleh_user", lazy=True, foreign_keys="Pengajuan.dibuat_oleh"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Pengajuan(db.Model):
    __tablename__ = "pengajuan"

    id = db.Column(db.Integer, primary_key=True)
    nama_pemohon = db.Column(db.String(150), nullable=False)

    # --- Data pemohon (sesuai fitur dataset) ---
    person_age = db.Column(db.Integer, nullable=False)
    person_income = db.Column(db.Float, nullable=False)
    person_home_ownership = db.Column(db.String(20), nullable=False)
    person_emp_length = db.Column(db.Float, nullable=False)
    loan_intent = db.Column(db.String(30), nullable=False)
    loan_grade = db.Column(db.String(5), nullable=True)  # sudah tidak dipakai sbg fitur model (lihat train_model.py), kolom dipertahankan utk data historis
    loan_amnt = db.Column(db.Float, nullable=False)
    loan_int_rate = db.Column(db.Float, nullable=False)
    loan_percent_income = db.Column(db.Float, nullable=False)
    cb_person_default_on_file = db.Column(db.String(3), nullable=False)
    cb_person_cred_hist_length = db.Column(db.Integer, nullable=False)

    # --- Hasil prediksi model ---
    skor_kredit = db.Column(db.Integer, nullable=False)
    probabilitas_default = db.Column(db.Float, nullable=False)
    rekomendasi_sistem = db.Column(db.String(20), nullable=False)  # 'Layak' / 'Berisiko Tinggi'
    faktor_risiko_json = db.Column(db.Text, nullable=True)

    # --- Keputusan analis ---
    keputusan_analis = db.Column(db.String(20), default="Menunggu")  # Menunggu/Disetujui/Ditolak
    catatan_analis = db.Column(db.Text, nullable=True)

    # --- Pembatalan (beda dari keputusan kredit -- ini soal validitas data) ---
    is_dibatalkan = db.Column(db.Boolean, default=False)
    catatan_pembatalan = db.Column(db.Text, nullable=True)

    # --- Hapus (soft-delete, masuk "tempat sampah" 30 hari) ---
    dihapus_pada = db.Column(db.DateTime, nullable=True)
    dihapus_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    dibuat_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    dibuat_pada = db.Column(db.DateTime, default=datetime.utcnow)
    diubah_pada = db.Column(db.DateTime, nullable=True)

    @property
    def batas_waktu_restore(self):
        if self.dihapus_pada:
            return self.dihapus_pada + timedelta(days=HAPUS_RETENSI_HARI)
        return None

    @property
    def sisa_hari_restore(self):
        if self.dihapus_pada:
            sisa = self.batas_waktu_restore - datetime.utcnow()
            return max(sisa.days, 0)
        return None

    def __repr__(self):
        return f"<Pengajuan {self.nama_pemohon} - {self.rekomendasi_sistem}>"


class LogAktivitas(db.Model):
    __tablename__ = "log_aktivitas"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    aksi = db.Column(db.String(50), nullable=False)  # mis. 'Edit Pengajuan', 'Hapus User', dll
    deskripsi = db.Column(db.Text, nullable=True)
    waktu = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<LogAktivitas {self.aksi} oleh user#{self.user_id}>"


def catat_log(user_id, aksi, deskripsi=None):
    """Helper untuk mencatat aktivitas ke log_aktivitas."""
    log = LogAktivitas(user_id=user_id, aksi=aksi, deskripsi=deskripsi)
    db.session.add(log)
