"""
app.py - Sistem Prediksi Kelayakan Kredit FinTech (XGBoost, Berbasis Web)
Aplikasi FULL v2: + edit/batalkan/hapus-restore pengajuan, export Excel/PDF,
ganti password & profil, log aktivitas, validasi input, grafik dashboard.
"""
import io
import json
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

import joblib
import pandas as pd
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, or_

from config import Config
from extensions import db, login_manager
from models import HAPUS_RETENSI_HARI, LogAktivitas, Pengajuan, User, catat_log

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "model")

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager.init_app(app)

# --- Muat model ML sekali saat aplikasi start ---
model = joblib.load(os.path.join(MODEL_DIR, "xgb_model.pkl"))
encoders = joblib.load(os.path.join(MODEL_DIR, "encoders.pkl"))
with open(os.path.join(MODEL_DIR, "metrics.json")) as f:
    METRICS = json.load(f)

FEATURE_COLUMNS = METRICS["feature_columns"]
LABEL_MAP = {fi["feature"]: fi["label"] for fi in METRICS["feature_importance"]}
IMPORTANCE_MAP = {fi["feature"]: fi["importance"] for fi in METRICS["feature_importance"]}

HOME_OWNERSHIP_LABELS = {"RENT": "Sewa", "OWN": "Milik Sendiri", "MORTGAGE": "KPR/Cicilan", "OTHER": "Lainnya"}
LOAN_INTENT_LABELS = {
    "PERSONAL": "Personal", "EDUCATION": "Pendidikan", "MEDICAL": "Medis",
    "VENTURE": "Modal Usaha", "HOMEIMPROVEMENT": "Renovasi Rumah", "DEBTCONSOLIDATION": "Konsolidasi Utang",
}


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Halaman ini hanya bisa diakses oleh Admin.", "danger")
            return redirect(url_for("dashboard"))
        return view_func(*args, **kwargs)
    return wrapper


def owner_or_admin_required(pengajuan):
    """True kalau current_user boleh mengelola (edit/batalkan/hapus/restore) pengajuan ini."""
    return current_user.is_admin or pengajuan.dibuat_oleh == current_user.id


# =========================================================
# VALIDASI INPUT
# =========================================================
def validasi_data_pemohon(form):
    errors = []
    try:
        age = float(form["person_age"])
        if not (18 <= age <= 100):
            errors.append("Usia harus di antara 18 dan 100 tahun.")
    except (ValueError, KeyError):
        errors.append("Usia tidak valid.")

    try:
        income = float(form["person_income"])
        if income <= 0:
            errors.append("Pendapatan tahunan harus lebih besar dari 0.")
    except (ValueError, KeyError):
        errors.append("Pendapatan tidak valid.")

    try:
        emp = float(form["person_emp_length"])
        if not (0 <= emp <= 60):
            errors.append("Lama bekerja harus di antara 0 dan 60 tahun.")
    except (ValueError, KeyError):
        errors.append("Lama bekerja tidak valid.")

    try:
        amnt = float(form["loan_amnt"])
        if amnt <= 0:
            errors.append("Jumlah pinjaman harus lebih besar dari 0.")
    except (ValueError, KeyError):
        errors.append("Jumlah pinjaman tidak valid.")

    try:
        rate = float(form["loan_int_rate"])
        if not (0 <= rate <= 40):
            errors.append("Suku bunga harus di antara 0 dan 40%.")
    except (ValueError, KeyError):
        errors.append("Suku bunga tidak valid.")

    try:
        hist = float(form["cb_person_cred_hist_length"])
        if hist < 0:
            errors.append("Lama riwayat kredit tidak boleh negatif.")
    except (ValueError, KeyError):
        errors.append("Lama riwayat kredit tidak valid.")

    if not form.get("nama_pemohon", "").strip():
        errors.append("Nama pemohon wajib diisi.")

    return errors


def jalankan_prediksi(form):
    """Ambil data form, jalankan model, kembalikan dict hasil + data mentah."""
    person_age = float(form["person_age"])
    person_income = float(form["person_income"])
    person_home_ownership = form["person_home_ownership"]
    person_emp_length = float(form["person_emp_length"])
    loan_intent = form["loan_intent"]
    loan_amnt = float(form["loan_amnt"])
    loan_int_rate = float(form["loan_int_rate"])
    cb_person_default_on_file = form["cb_person_default_on_file"]
    cb_person_cred_hist_length = float(form["cb_person_cred_hist_length"])
    loan_percent_income = round(loan_amnt / person_income, 4) if person_income else 0

    row_raw = {
        "person_age": person_age, "person_income": person_income,
        "person_emp_length": person_emp_length, "loan_amnt": loan_amnt,
        "loan_int_rate": loan_int_rate, "loan_percent_income": loan_percent_income,
        "cb_person_cred_hist_length": cb_person_cred_hist_length,
        "person_home_ownership": encoders["person_home_ownership"][person_home_ownership],
        "loan_intent": encoders["loan_intent"][loan_intent],
        "cb_person_default_on_file": encoders["cb_person_default_on_file"][cb_person_default_on_file],
    }

    X = pd.DataFrame([row_raw])[FEATURE_COLUMNS]
    proba_default = float(model.predict_proba(X)[0, 1])
    pred = int(proba_default > 0.5)
    skor_kredit = int(round((1 - proba_default) * 850))
    status = "Berisiko Tinggi" if pred == 1 else "Layak"

    flags = {
        "cb_person_default_on_file": cb_person_default_on_file == "Y",
        "loan_percent_income": loan_percent_income > 0.35,
        "loan_int_rate": loan_int_rate > 15,
        "person_emp_length": person_emp_length < 1,
    }
    faktor_risiko = [
        {"feature": LABEL_MAP[feat], "weight": IMPORTANCE_MAP.get(feat, 0)}
        for feat, risky in flags.items() if risky
    ]
    faktor_risiko.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "nama_pemohon": form["nama_pemohon"].strip(),
        "person_age": person_age, "person_income": person_income,
        "person_home_ownership": person_home_ownership, "person_emp_length": person_emp_length,
        "loan_intent": loan_intent, "loan_amnt": loan_amnt,
        "loan_int_rate": loan_int_rate, "loan_percent_income": loan_percent_income,
        "cb_person_default_on_file": cb_person_default_on_file,
        "cb_person_cred_hist_length": cb_person_cred_hist_length,
        "skor_kredit": skor_kredit, "probabilitas_default": round(proba_default, 4),
        "rekomendasi_sistem": status, "faktor_risiko": faktor_risiko[:5],
    }


def bersihkan_sampah_kedaluwarsa():
    """Hard-delete data yang sudah lewat masa retensi tempat sampah."""
    batas = datetime.utcnow() - timedelta(days=HAPUS_RETENSI_HARI)
    kedaluwarsa = Pengajuan.query.filter(
        Pengajuan.dihapus_pada.isnot(None), Pengajuan.dihapus_pada < batas
    ).all()
    for p in kedaluwarsa:
        db.session.delete(p)
    if kedaluwarsa:
        db.session.commit()


# =========================================================
# AUTENTIKASI
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.aktif and user.check_password(password):
            login_user(user)
            flash(f"Selamat datang, {user.nama_lengkap}!", "success")
            return redirect(url_for("dashboard"))
        elif user and not user.aktif:
            flash("Akun Anda telah dinonaktifkan. Hubungi Admin.", "danger")
        else:
            flash("Username atau password salah.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Anda telah logout.", "info")
    return redirect(url_for("login"))


# =========================================================
# PROFIL SAYA (edit nama & ganti password)
# =========================================================
@app.route("/profil", methods=["GET", "POST"])
@login_required
def profil():
    if request.method == "POST":
        aksi = request.form.get("aksi")

        if aksi == "update_nama":
            nama_baru = request.form.get("nama_lengkap", "").strip()
            if nama_baru:
                current_user.nama_lengkap = nama_baru
                db.session.commit()
                flash("Nama berhasil diperbarui.", "success")
            else:
                flash("Nama tidak boleh kosong.", "danger")

        elif aksi == "ganti_password":
            password_lama = request.form.get("password_lama", "")
            password_baru = request.form.get("password_baru", "")
            konfirmasi = request.form.get("konfirmasi_password", "")

            if not current_user.check_password(password_lama):
                flash("Password lama salah.", "danger")
            elif len(password_baru) < 6:
                flash("Password baru minimal 6 karakter.", "danger")
            elif password_baru != konfirmasi:
                flash("Konfirmasi password baru tidak cocok.", "danger")
            else:
                current_user.set_password(password_baru)
                catat_log(current_user.id, "Ganti Password", "Mengganti password sendiri")
                db.session.commit()
                flash("Password berhasil diganti.", "success")

        return redirect(url_for("profil"))

    return render_template("profil.html")


# =========================================================
# DASHBOARD
# =========================================================
@app.route("/")
@login_required
def dashboard():
    today = datetime.utcnow().date()
    start_month = today.replace(day=1)
    base_query = Pengajuan.query.filter(Pengajuan.dihapus_pada.is_(None))

    total_hari_ini = base_query.filter(func.date(Pengajuan.dibuat_pada) == today).count()
    total_bulan_ini = base_query.filter(Pengajuan.dibuat_pada >= start_month).count()
    total_layak = base_query.filter_by(rekomendasi_sistem="Layak", is_dibatalkan=False).count()
    total_berisiko = base_query.filter_by(rekomendasi_sistem="Berisiko Tinggi", is_dibatalkan=False).count()
    total_semua = total_layak + total_berisiko
    persen_layak = round((total_layak / total_semua) * 100, 1) if total_semua else 0

    pengajuan_terbaru = base_query.order_by(Pengajuan.dibuat_pada.desc()).limit(5).all()

    grafik_per_analis = []
    if current_user.is_admin:
        hasil = (
            db.session.query(User.nama_lengkap, func.count(Pengajuan.id))
            .join(Pengajuan, Pengajuan.dibuat_oleh == User.id)
            .filter(Pengajuan.dihapus_pada.is_(None))
            .group_by(User.nama_lengkap)
            .all()
        )
        grafik_per_analis = [{"nama": nama, "jumlah": jumlah} for nama, jumlah in hasil]

    return render_template(
        "dashboard.html",
        total_hari_ini=total_hari_ini, total_bulan_ini=total_bulan_ini,
        total_layak=total_layak, total_berisiko=total_berisiko, persen_layak=persen_layak,
        pengajuan_terbaru=pengajuan_terbaru, grafik_per_analis=grafik_per_analis,
    )


# =========================================================
# PREDIKSI KREDIT (Input Data Pemohon -> Hasil)
# =========================================================
@app.route("/prediksi", methods=["GET", "POST"])
@login_required
def prediksi():
    if request.method == "POST":
        errors = validasi_data_pemohon(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("prediksi.html", form_data=request.form)

        try:
            hasil = jalankan_prediksi(request.form)
        except (KeyError, ValueError) as e:
            flash(f"Input tidak valid: {e}", "danger")
            return render_template("prediksi.html", form_data=request.form)

        pengajuan = Pengajuan(
            nama_pemohon=hasil["nama_pemohon"], person_age=hasil["person_age"],
            person_income=hasil["person_income"], person_home_ownership=hasil["person_home_ownership"],
            person_emp_length=hasil["person_emp_length"], loan_intent=hasil["loan_intent"],
            loan_amnt=hasil["loan_amnt"],
            loan_int_rate=hasil["loan_int_rate"], loan_percent_income=hasil["loan_percent_income"],
            cb_person_default_on_file=hasil["cb_person_default_on_file"],
            cb_person_cred_hist_length=hasil["cb_person_cred_hist_length"],
            skor_kredit=hasil["skor_kredit"], probabilitas_default=hasil["probabilitas_default"],
            rekomendasi_sistem=hasil["rekomendasi_sistem"],
            faktor_risiko_json=json.dumps(hasil["faktor_risiko"]),
            keputusan_analis="Menunggu", dibuat_oleh=current_user.id,
        )
        db.session.add(pengajuan)
        db.session.flush()
        catat_log(current_user.id, "Buat Pengajuan", f"Pengajuan baru: {pengajuan.nama_pemohon}")
        db.session.commit()

        return redirect(url_for("detail_pengajuan", pengajuan_id=pengajuan.id))

    return render_template("prediksi.html", form_data=None)


# =========================================================
# DETAIL PENGAJUAN & KONFIRMASI KEPUTUSAN ANALIS
# =========================================================
@app.route("/pengajuan/<int:pengajuan_id>", methods=["GET", "POST"])
@login_required
def detail_pengajuan(pengajuan_id):
    pengajuan = Pengajuan.query.get_or_404(pengajuan_id)
    if pengajuan.dihapus_pada is not None:
        abort(404)

    if request.method == "POST":
        keputusan = request.form.get("keputusan")
        catatan = request.form.get("catatan", "").strip()
        if keputusan in ("Disetujui", "Ditolak", "Menunggu"):
            pengajuan.keputusan_analis = keputusan
            pengajuan.catatan_analis = catatan
            db.session.commit()
            flash("Keputusan berhasil disimpan.", "success")
        return redirect(url_for("detail_pengajuan", pengajuan_id=pengajuan.id))

    faktor_risiko = json.loads(pengajuan.faktor_risiko_json or "[]")
    bisa_kelola = owner_or_admin_required(pengajuan)
    return render_template(
        "detail_pengajuan.html", p=pengajuan, faktor_risiko=faktor_risiko, bisa_kelola=bisa_kelola,
        home_label=HOME_OWNERSHIP_LABELS.get(pengajuan.person_home_ownership, pengajuan.person_home_ownership),
        intent_label=LOAN_INTENT_LABELS.get(pengajuan.loan_intent, pengajuan.loan_intent),
    )


# =========================================================
# EDIT PENGAJUAN
# =========================================================
@app.route("/pengajuan/<int:pengajuan_id>/edit", methods=["GET", "POST"])
@login_required
def edit_pengajuan(pengajuan_id):
    pengajuan = Pengajuan.query.get_or_404(pengajuan_id)
    if pengajuan.dihapus_pada is not None:
        abort(404)
    if not owner_or_admin_required(pengajuan):
        flash("Anda tidak berwenang mengedit pengajuan ini.", "danger")
        return redirect(url_for("riwayat"))

    if request.method == "POST":
        errors = validasi_data_pemohon(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("edit_pengajuan.html", p=pengajuan, form_data=request.form)

        try:
            hasil = jalankan_prediksi(request.form)
        except (KeyError, ValueError) as e:
            flash(f"Input tidak valid: {e}", "danger")
            return render_template("edit_pengajuan.html", p=pengajuan, form_data=request.form)

        for field in [
            "nama_pemohon", "person_age", "person_income", "person_home_ownership",
            "person_emp_length", "loan_intent", "loan_amnt", "loan_int_rate",
            "loan_percent_income", "cb_person_default_on_file", "cb_person_cred_hist_length",
            "skor_kredit", "probabilitas_default", "rekomendasi_sistem",
        ]:
            setattr(pengajuan, field, hasil[field])
        pengajuan.faktor_risiko_json = json.dumps(hasil["faktor_risiko"])
        pengajuan.diubah_pada = datetime.utcnow()

        catat_log(current_user.id, "Edit Pengajuan", f"Mengedit pengajuan #{pengajuan.id} ({pengajuan.nama_pemohon})")
        db.session.commit()
        flash("Data pengajuan berhasil diperbarui, prediksi dihitung ulang.", "success")
        return redirect(url_for("detail_pengajuan", pengajuan_id=pengajuan.id))

    return render_template("edit_pengajuan.html", p=pengajuan, form_data=None)


# =========================================================
# BATALKAN / AKTIFKAN KEMBALI PENGAJUAN
# =========================================================
@app.route("/pengajuan/<int:pengajuan_id>/batalkan", methods=["POST"])
@login_required
def batalkan_pengajuan(pengajuan_id):
    pengajuan = Pengajuan.query.get_or_404(pengajuan_id)
    if not owner_or_admin_required(pengajuan):
        flash("Anda tidak berwenang membatalkan pengajuan ini.", "danger")
        return redirect(url_for("riwayat"))

    pengajuan.is_dibatalkan = not pengajuan.is_dibatalkan
    if pengajuan.is_dibatalkan:
        pengajuan.catatan_pembatalan = request.form.get("catatan_pembatalan", "").strip()
        catat_log(current_user.id, "Batalkan Pengajuan", f"Membatalkan pengajuan #{pengajuan.id}")
        flash("Pengajuan ditandai sebagai dibatalkan (data tidak valid).", "warning")
    else:
        catat_log(current_user.id, "Aktifkan Kembali Pengajuan", f"Mengaktifkan kembali pengajuan #{pengajuan.id}")
        flash("Pembatalan dibatalkan, pengajuan aktif kembali.", "success")

    db.session.commit()
    return redirect(url_for("detail_pengajuan", pengajuan_id=pengajuan.id))


# =========================================================
# HAPUS (soft-delete) & TEMPAT SAMPAH
# =========================================================
@app.route("/pengajuan/<int:pengajuan_id>/hapus", methods=["POST"])
@login_required
def hapus_pengajuan(pengajuan_id):
    pengajuan = Pengajuan.query.get_or_404(pengajuan_id)
    if not owner_or_admin_required(pengajuan):
        flash("Anda tidak berwenang menghapus pengajuan ini.", "danger")
        return redirect(url_for("riwayat"))

    pengajuan.dihapus_pada = datetime.utcnow()
    pengajuan.dihapus_oleh = current_user.id
    catat_log(current_user.id, "Hapus Pengajuan", f"Menghapus pengajuan #{pengajuan.id} ({pengajuan.nama_pemohon})")
    db.session.commit()
    flash(f"Pengajuan dipindahkan ke Tempat Sampah. Bisa dipulihkan dalam {HAPUS_RETENSI_HARI} hari.", "warning")
    return redirect(url_for("riwayat"))


@app.route("/sampah")
@login_required
def sampah():
    bersihkan_sampah_kedaluwarsa()
    query = Pengajuan.query.filter(Pengajuan.dihapus_pada.isnot(None))
    if not current_user.is_admin:
        query = query.filter(Pengajuan.dibuat_oleh == current_user.id)
    daftar = query.order_by(Pengajuan.dihapus_pada.desc()).all()
    return render_template("sampah.html", daftar=daftar)


@app.route("/pengajuan/<int:pengajuan_id>/restore", methods=["POST"])
@login_required
def restore_pengajuan(pengajuan_id):
    pengajuan = Pengajuan.query.get_or_404(pengajuan_id)
    if not owner_or_admin_required(pengajuan):
        flash("Anda tidak berwenang memulihkan pengajuan ini.", "danger")
        return redirect(url_for("sampah"))

    pengajuan.dihapus_pada = None
    pengajuan.dihapus_oleh = None
    catat_log(current_user.id, "Pulihkan Pengajuan", f"Memulihkan pengajuan #{pengajuan.id} dari tempat sampah")
    db.session.commit()
    flash("Pengajuan berhasil dipulihkan.", "success")
    return redirect(url_for("sampah"))


@app.route("/pengajuan/<int:pengajuan_id>/hapus-permanen", methods=["POST"])
@login_required
@admin_required
def hapus_permanen_pengajuan(pengajuan_id):
    pengajuan = Pengajuan.query.get_or_404(pengajuan_id)
    catat_log(current_user.id, "Hapus Permanen", f"Menghapus permanen pengajuan #{pengajuan.id} ({pengajuan.nama_pemohon})")
    db.session.delete(pengajuan)
    db.session.commit()
    flash("Pengajuan dihapus permanen.", "success")
    return redirect(url_for("sampah"))


# =========================================================
# RIWAYAT PENGAJUAN
# =========================================================
@app.route("/riwayat")
@login_required
def riwayat():
    query = Pengajuan.query.filter(Pengajuan.dihapus_pada.is_(None))
    if not current_user.is_admin:
        query = query.filter(Pengajuan.dibuat_oleh == current_user.id)

    keyword = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "")
    analis_filter = request.args.get("analis", "")

    if keyword:
        query = query.filter(Pengajuan.nama_pemohon.ilike(f"%{keyword}%"))
    if status_filter == "Dibatalkan":
        query = query.filter(Pengajuan.is_dibatalkan.is_(True))
    elif status_filter:
        query = query.filter(Pengajuan.rekomendasi_sistem == status_filter, Pengajuan.is_dibatalkan.is_(False))
    if analis_filter and current_user.is_admin:
        query = query.filter(Pengajuan.dibuat_oleh == int(analis_filter))

    daftar_pengajuan = query.order_by(Pengajuan.dibuat_pada.desc()).limit(200).all()

    daftar_analis = User.query.order_by(User.nama_lengkap).all() if current_user.is_admin else []

    return render_template(
        "riwayat.html", daftar_pengajuan=daftar_pengajuan, keyword=keyword,
        status_filter=status_filter, analis_filter=analis_filter, daftar_analis=daftar_analis,
    )


@app.route("/riwayat/export/excel")
@login_required
def export_excel():
    query = Pengajuan.query.filter(Pengajuan.dihapus_pada.is_(None))
    if not current_user.is_admin:
        query = query.filter(Pengajuan.dibuat_oleh == current_user.id)
    daftar = query.order_by(Pengajuan.dibuat_pada.desc()).all()

    rows = []
    for p in daftar:
        rows.append({
            "Nama Pemohon": p.nama_pemohon, "Usia": p.person_age,
            "Pendapatan Tahunan": p.person_income, "Status Rumah": p.person_home_ownership,
            "Lama Bekerja (th)": p.person_emp_length, "Tujuan Pinjaman": p.loan_intent,
            "Jumlah Pinjaman": p.loan_amnt,
            "Suku Bunga (%)": p.loan_int_rate, "Rasio Pinjaman/Pendapatan": p.loan_percent_income,
            "Riwayat Gagal Bayar": p.cb_person_default_on_file,
            "Skor Kredit": p.skor_kredit, "Rekomendasi Sistem": p.rekomendasi_sistem,
            "Keputusan Analis": p.keputusan_analis,
            "Dibatalkan": "Ya" if p.is_dibatalkan else "Tidak",
            "Diajukan Oleh": p.dibuat_oleh_user.nama_lengkap,
            "Tanggal": p.dibuat_pada.strftime("%d/%m/%Y %H:%M"),
        })

    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Riwayat Pengajuan")
    buffer.seek(0)

    catat_log(current_user.id, "Export Excel", f"Mengekspor {len(rows)} baris riwayat pengajuan")
    db.session.commit()

    return send_file(
        buffer, as_attachment=True,
        download_name=f"riwayat_pengajuan_{datetime.utcnow().strftime('%Y%m%d')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =========================================================
# LAPORAN (Admin) - metrik model & statistik agregat
# =========================================================
@app.route("/laporan")
@login_required
@admin_required
def laporan():
    base_query = Pengajuan.query.filter(Pengajuan.dihapus_pada.is_(None))
    total_pengajuan = base_query.count()
    total_disetujui = base_query.filter_by(keputusan_analis="Disetujui").count()
    total_ditolak = base_query.filter_by(keputusan_analis="Ditolak").count()
    total_menunggu = base_query.filter_by(keputusan_analis="Menunggu").count()
    total_dibatalkan = base_query.filter_by(is_dibatalkan=True).count()

    tren = []
    for i in range(6, -1, -1):
        tanggal = (datetime.utcnow() - timedelta(days=i)).date()
        jumlah = base_query.filter(func.date(Pengajuan.dibuat_pada) == tanggal).count()
        tren.append({"tanggal": tanggal.strftime("%d/%m"), "jumlah": jumlah})

    return render_template(
        "laporan.html", metrics=METRICS, total_pengajuan=total_pengajuan,
        total_disetujui=total_disetujui, total_ditolak=total_ditolak,
        total_menunggu=total_menunggu, total_dibatalkan=total_dibatalkan, tren=tren,
    )


@app.route("/laporan/export/pdf")
@login_required
@admin_required
def export_pdf():
    base_query = Pengajuan.query.filter(Pengajuan.dihapus_pada.is_(None))
    total_pengajuan = base_query.count()
    total_disetujui = base_query.filter_by(keputusan_analis="Disetujui").count()
    total_ditolak = base_query.filter_by(keputusan_analis="Ditolak").count()
    total_menunggu = base_query.filter_by(keputusan_analis="Menunggu").count()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Laporan Sistem Prediksi Kelayakan Kredit FinTech", styles["Title"]))
    elements.append(Paragraph(f"Dibuat pada: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC", styles["Normal"]))
    elements.append(Spacer(1, 16))

    elements.append(Paragraph("Ringkasan Pengajuan", styles["Heading2"]))
    ringkasan_data = [
        ["Total Pengajuan", str(total_pengajuan)],
        ["Disetujui", str(total_disetujui)],
        ["Ditolak", str(total_ditolak)],
        ["Menunggu Peninjauan", str(total_menunggu)],
    ]
    t1 = Table(ringkasan_data, colWidths=[250, 150])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1C2B4A")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t1)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Evaluasi Model (Data Uji)", styles["Heading2"]))
    model_data = [["Model", "Akurasi", "Presisi", "Recall", "F1-Score", "ROC-AUC"]]
    for r in METRICS["results"]:
        model_data.append([
            r["model"], f"{r['accuracy']*100:.1f}%", f"{r['precision']*100:.1f}%",
            f"{r['recall']*100:.1f}%", f"{r['f1_score']*100:.1f}%", f"{r['roc_auc']:.3f}",
        ])
    t2 = Table(model_data, colWidths=[110, 70, 70, 70, 70, 70])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C9A227")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t2)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Faktor yang Memengaruhi Keputusan Kredit", styles["Heading2"]))
    feat_data = [["Atribut", "Tingkat Pengaruh"]]
    for fi in METRICS["feature_importance"]:
        feat_data.append([fi["label"], f"{fi['importance']*100:.1f}%"])
    t3 = Table(feat_data, colWidths=[300, 120])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1C2B4A")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t3)

    doc.build(elements)
    buffer.seek(0)

    catat_log(current_user.id, "Export PDF", "Mengekspor laporan evaluasi model ke PDF")
    db.session.commit()

    return send_file(
        buffer, as_attachment=True,
        download_name=f"laporan_kredit_{datetime.utcnow().strftime('%Y%m%d')}.pdf",
        mimetype="application/pdf",
    )


# =========================================================
# KELOLA USER (Admin)
# =========================================================
@app.route("/users")
@login_required
@admin_required
def kelola_user():
    daftar_user = User.query.order_by(User.dibuat_pada.desc()).all()
    return render_template("kelola_user.html", daftar_user=daftar_user)


@app.route("/users/tambah", methods=["POST"])
@login_required
@admin_required
def tambah_user():
    nama_lengkap = request.form.get("nama_lengkap", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "analis")

    if not (nama_lengkap and username and password):
        flash("Semua field wajib diisi.", "danger")
        return redirect(url_for("kelola_user"))
    if User.query.filter_by(username=username).first():
        flash("Username sudah digunakan.", "danger")
        return redirect(url_for("kelola_user"))

    user_baru = User(nama_lengkap=nama_lengkap, username=username, role=role)
    user_baru.set_password(password)
    db.session.add(user_baru)
    db.session.flush()
    catat_log(current_user.id, "Tambah User", f"Menambahkan user '{username}' ({role})")
    db.session.commit()
    flash(f"User '{username}' berhasil ditambahkan.", "success")
    return redirect(url_for("kelola_user"))


@app.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        nama_lengkap = request.form.get("nama_lengkap", "").strip()
        username = request.form.get("username", "").strip()
        role = request.form.get("role", user.role)

        existing = User.query.filter_by(username=username).first()
        if existing and existing.id != user.id:
            flash("Username sudah digunakan user lain.", "danger")
            return render_template("edit_user.html", u=user)

        user.nama_lengkap = nama_lengkap or user.nama_lengkap
        user.username = username or user.username
        user.role = role
        catat_log(current_user.id, "Edit User", f"Mengedit data user '{user.username}'")
        db.session.commit()
        flash("Data user berhasil diperbarui.", "success")
        return redirect(url_for("kelola_user"))

    return render_template("edit_user.html", u=user)


@app.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Anda tidak bisa menonaktifkan akun sendiri.", "danger")
        return redirect(url_for("kelola_user"))
    user.aktif = not user.aktif
    catat_log(current_user.id, "Toggle Status User", f"{'Mengaktifkan' if user.aktif else 'Menonaktifkan'} user '{user.username}'")
    db.session.commit()
    status = "diaktifkan" if user.aktif else "dinonaktifkan"
    flash(f"User '{user.username}' berhasil {status}.", "success")
    return redirect(url_for("kelola_user"))


@app.route("/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    password_baru = secrets.token_urlsafe(6)
    user.set_password(password_baru)
    catat_log(current_user.id, "Reset Password", f"Mereset password user '{user.username}'")
    db.session.commit()
    flash(f"Password '{user.username}' berhasil direset menjadi: {password_baru} — segera beritahu user ini secara langsung.", "success")
    return redirect(url_for("kelola_user"))


# =========================================================
# LOG AKTIVITAS (Admin)
# =========================================================
@app.route("/log-aktivitas")
@login_required
@admin_required
def log_aktivitas():
    logs = LogAktivitas.query.order_by(LogAktivitas.waktu.desc()).limit(300).all()
    return render_template("log_aktivitas.html", logs=logs)


# =========================================================
# API metrics (untuk grafik/chart di frontend)
# =========================================================
@app.route("/api/metrics")
@login_required
def api_metrics():
    return jsonify(METRICS)


# =========================================================
# ERROR HANDLERS
# =========================================================
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, pesan="Halaman yang kamu cari tidak ditemukan."), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, pesan="Kamu tidak punya izin mengakses halaman ini."), 403


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, pesan="Terjadi kesalahan pada server."), 500


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5050, debug=debug_mode)
