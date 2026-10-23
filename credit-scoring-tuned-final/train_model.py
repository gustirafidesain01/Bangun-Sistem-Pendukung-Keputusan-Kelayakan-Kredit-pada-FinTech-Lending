"""
train_model.py (FINAL PIPELINE)
---------------------------------
Melatih model prediksi kelayakan kredit dengan pipeline yang sudah diperbaiki
sesuai kesepakatan diskusi metodologi:

  1. Split train-test DULU, baru imputasi missing value (median dari data latih saja)
     -> mencegah data leakage dari data uji ke proses training.
  2. SMOTENC (bukan SMOTE biasa) untuk menangani imbalanced data
     -> mencegah SMOTE menghasilkan nilai kategorikal pecahan yang tidak valid.
  3. Encoding berbeda sesuai karakteristik model:
       - XGBoost & Random Forest -> Label Encoding (aman untuk model pohon)
       - Logistic Regression     -> One-Hot Encoding (adil untuk model linear)
  4. Fitur loan_grade DIKELUARKAN dari model (hasil ablation study menunjukkan
     penurunan performa sangat kecil, dan loan_grade berpotensi sirkular secara
     konseptual karena sudah merupakan representasi penilaian risiko).

Model yang disimpan (dipakai aplikasi web) adalah XGBoost dengan Label Encoding,
dilatih pada 10 fitur (tanpa loan_grade).
"""
import json
import os
import time

import joblib
import pandas as pd
from imblearn.over_sampling import SMOTENC
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import RandomizedSearchCV, train_test_split
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

RANDOM_STATE = 42
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "credit_risk_dataset.csv")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "model")

# loan_grade SENGAJA TIDAK DIMASUKKAN (lihat catatan di docstring atas)
CATEGORICAL_COLUMNS = ["person_home_ownership", "loan_intent", "cb_person_default_on_file"]
NUMERIC_COLUMNS = [
    "person_age", "person_income", "person_emp_length", "loan_amnt",
    "loan_int_rate", "loan_percent_income", "cb_person_cred_hist_length",
]
FEATURE_COLUMNS = NUMERIC_COLUMNS + CATEGORICAL_COLUMNS
TARGET_COLUMN = "loan_status"

FEATURE_LABELS_ID = {
    "person_age": "Usia Pemohon",
    "person_income": "Pendapatan Tahunan",
    "person_emp_length": "Lama Masa Kerja (tahun)",
    "loan_amnt": "Jumlah Pinjaman Diajukan",
    "loan_int_rate": "Suku Bunga Pinjaman (%)",
    "loan_percent_income": "Rasio Pinjaman terhadap Pendapatan",
    "cb_person_cred_hist_length": "Lama Riwayat Kredit (tahun)",
    "person_home_ownership": "Status Kepemilikan Rumah",
    "loan_intent": "Tujuan Pinjaman",
    "cb_person_default_on_file": "Riwayat Gagal Bayar Sebelumnya",
}


def load_and_clean_data():
    df = pd.read_csv(DATA_PATH)
    before = len(df)
    df = df[df["person_age"] <= 80].reset_index(drop=True)
    print(f"[Cleaning] Menghapus {before - len(df)} baris outlier (usia > 80 tahun)")
    return df


def evaluate(model, X_test, y_test, name):
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    return {
        "model": name,
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "precision": round(precision_score(y_test, y_pred), 4),
        "recall": round(recall_score(y_test, y_pred), 4),
        "f1_score": round(f1_score(y_test, y_pred), 4),
        "roc_auc": round(roc_auc_score(y_test, y_proba), 4),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
    }


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    df = load_and_clean_data()

    # --- Label-encode kategorikal (basis untuk XGBoost/RF & SMOTENC) ---
    encoders = {}
    df_enc = df.copy()
    for col in CATEGORICAL_COLUMNS:
        le = LabelEncoder()
        df_enc[col] = le.fit_transform(df_enc[col].astype(str))
        encoders[col] = {cls: int(idx) for idx, cls in enumerate(le.classes_)}

    X = df_enc[FEATURE_COLUMNS].copy()
    y = df_enc[TARGET_COLUMN]

    # --- FIX #1: split DULU, baru imputasi (mencegah data leakage) ---
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )
    for col in ["person_emp_length", "loan_int_rate"]:
        median_train = X_train[col].median()
        missing_train = X_train[col].isna().sum()
        missing_test = X_test[col].isna().sum()
        X_train[col] = X_train[col].fillna(median_train)
        X_test[col] = X_test[col].fillna(median_train)  # median dari TRAIN, bukan dari test
        print(f"[Missing Value] '{col}': {missing_train} (train) + {missing_test} (test) diisi median TRAIN={median_train:.2f}")

    # --- FIX #2: SMOTENC (bukan SMOTE biasa) ---
    cat_indices = [FEATURE_COLUMNS.index(c) for c in CATEGORICAL_COLUMNS]
    print(f"[SMOTENC] Distribusi sebelum: {y_train.value_counts().to_dict()}")
    smotenc = SMOTENC(categorical_features=cat_indices, random_state=RANDOM_STATE)
    X_train_res, y_train_res = smotenc.fit_resample(X_train, y_train)
    print(f"[SMOTENC] Distribusi sesudah: {pd.Series(y_train_res).value_counts().to_dict()}")
    for col in CATEGORICAL_COLUMNS:
        assert (X_train_res[col] % 1 == 0).all(), f"Kolom {col} punya nilai pecahan!"
    print("[Verifikasi] Semua kolom kategorikal hasil SMOTENC tetap valid (tidak ada nilai pecahan)")

    results = []

    # --- XGBoost BASELINE (parameter manual, sebelum tuning) — untuk perbandingan Bab IV ---
    xgb_baseline = XGBClassifier(
        n_estimators=300, max_depth=5, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9, eval_metric="logloss", random_state=RANDOM_STATE,
    )
    xgb_baseline.fit(X_train_res, y_train_res)
    hasil_baseline = evaluate(xgb_baseline, X_test, y_test, "XGBoost (Sebelum Tuning)")
    results.append(hasil_baseline)
    print(f"\n[Baseline] acc={hasil_baseline['accuracy']:.4f}  f1={hasil_baseline['f1_score']:.4f}  auc={hasil_baseline['roc_auc']:.4f}")

    # --- FIX #6: Hyperparameter Tuning XGBoost ---
    # SMOTENC di-nest di DALAM setiap fold cross-validation (bukan sekali di awal),
    # supaya data sintetis tidak "bocor" antar fold latih/validasi -> lebih ketat
    # daripada praktik umum yang menerapkan SMOTE sekali sebelum CV.
    print("\n[Tuning] Menjalankan RandomizedSearchCV (bisa beberapa menit)...")
    t0 = time.time()

    pipeline_xgb = ImbPipeline([
        ("smotenc", SMOTENC(categorical_features=cat_indices, random_state=RANDOM_STATE)),
        ("clf", XGBClassifier(eval_metric="logloss", random_state=RANDOM_STATE)),
    ])

    param_distributions = {
        "clf__n_estimators": [100, 150, 200, 300, 400, 500],
        "clf__max_depth": [3, 4, 5, 6, 7, 8],
        "clf__learning_rate": [0.01, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2],
        "clf__subsample": [0.6, 0.7, 0.8, 0.9, 1.0],
        "clf__colsample_bytree": [0.6, 0.7, 0.8, 0.9, 1.0],
        "clf__min_child_weight": [1, 3, 5],
    }

    search = RandomizedSearchCV(
        pipeline_xgb, param_distributions=param_distributions,
        n_iter=15, cv=3, scoring="f1", random_state=RANDOM_STATE,
        n_jobs=1, verbose=2,
    )
    # Dilatih pada X_train MENTAH (belum di-SMOTENC manual) -> SMOTENC dijalankan
    # otomatis di dalam pipeline, khusus pada bagian latih tiap fold CV.
    search.fit(X_train, y_train)

    elapsed = time.time() - t0
    print(f"[Tuning] Selesai dalam {elapsed:.1f} detik")
    print(f"[Tuning] Parameter terbaik: {search.best_params_}")
    print(f"[Tuning] Skor F1 terbaik (cross-validation): {search.best_score_:.4f}")

    best_pipeline = search.best_estimator_  # Pipeline(SMOTENC + XGBoost) siap pakai
    xgb = best_pipeline  # INI yang disimpan & dipakai aplikasi (model/xgb_model.pkl)

    hasil_tuned = evaluate(best_pipeline, X_test, y_test, "XGBoost")
    results.append(hasil_tuned)
    print(f"[Tuning] Hasil pada data uji: acc={hasil_tuned['accuracy']:.4f}  f1={hasil_tuned['f1_score']:.4f}  auc={hasil_tuned['roc_auc']:.4f}")

    print("\n[Perbandingan] Sebelum vs Sesudah Tuning:")
    for metrik in ["accuracy", "precision", "recall", "f1_score", "roc_auc"]:
        selisih = hasil_tuned[metrik] - hasil_baseline[metrik]
        print(f"  {metrik:<12} sebelum={hasil_baseline[metrik]:.4f}   sesudah={hasil_tuned[metrik]:.4f}   selisih={selisih:+.4f}")

    # --- Random Forest (Label Encoding, pembanding) ---
    rf = RandomForestClassifier(n_estimators=300, max_depth=10, random_state=RANDOM_STATE)
    rf.fit(X_train_res, y_train_res)
    results.append(evaluate(rf, X_test, y_test, "Random Forest"))

    # --- FIX #3: Logistic Regression pakai One-Hot Encoding (pembanding) ---
    ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    ohe.fit(X_train_res[CATEGORICAL_COLUMNS])

    def to_onehot_matrix(X_part):
        num_part = X_part[NUMERIC_COLUMNS].reset_index(drop=True)
        cat_part = pd.DataFrame(
            ohe.transform(X_part[CATEGORICAL_COLUMNS]),
            columns=ohe.get_feature_names_out(CATEGORICAL_COLUMNS),
        ).reset_index(drop=True)
        return pd.concat([num_part, cat_part], axis=1)

    X_train_ohe = to_onehot_matrix(X_train_res)
    X_test_ohe = to_onehot_matrix(X_test)

    scaler = StandardScaler()
    X_train_ohe_scaled = scaler.fit_transform(X_train_ohe)
    X_test_ohe_scaled = scaler.transform(X_test_ohe)

    logreg = LogisticRegression(max_iter=1000)
    logreg.fit(X_train_ohe_scaled, y_train_res)
    results.append(evaluate(logreg, X_test_ohe_scaled, y_test, "Logistic Regression"))

    # --- Feature importance dari XGBoost hasil tuning (model utama aplikasi) ---
    importances = best_pipeline.named_steps["clf"].feature_importances_
    feat_importance = sorted(
        [
            {"feature": f, "label": FEATURE_LABELS_ID[f], "importance": round(float(imp), 4)}
            for f, imp in zip(FEATURE_COLUMNS, importances)
        ],
        key=lambda x: x["importance"], reverse=True,
    )

    joblib.dump(xgb, os.path.join(MODEL_DIR, "xgb_model.pkl"))
    joblib.dump(encoders, os.path.join(MODEL_DIR, "encoders.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.pkl"))  # untuk referensi/reproduksi LR

    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump(
            {
                "results": results,
                "feature_importance": feat_importance,
                "feature_columns": FEATURE_COLUMNS,
                "categorical_columns": CATEGORICAL_COLUMNS,
                "numeric_columns": NUMERIC_COLUMNS,
                "n_train": len(X_train_res),
                "n_test": len(X_test),
                "n_train_original": len(X_train),
                "target_distribution_original": y.value_counts(normalize=True).round(3).to_dict(),
                "dataset_source": "Kaggle - Credit Risk Dataset (laotse)",
                "dataset_rows_used": len(df),
                "pipeline_notes": (
                    "loan_grade dikeluarkan dari fitur (ablation study menunjukkan penurunan "
                    "performa minimal dan berpotensi sirkular secara konseptual). Preprocessing: "
                    "split sebelum imputasi (mencegah leakage), SMOTENC (menjaga validitas kategori "
                    "saat oversampling), encoding berbeda per model (Label untuk XGBoost/RF, "
                    "One-Hot untuk Logistic Regression)."
                ),
                "hyperparameter_tuning": {
                    "method": "RandomizedSearchCV (n_iter=30, cv=5, scoring=f1)",
                    "note": (
                        "SMOTENC dijalankan di dalam setiap fold cross-validation (bukan sekali "
                        "di awal) untuk mencegah data sintetis bocor antar fold latih/validasi."
                    ),
                    "best_params": {k.replace("clf__", ""): v for k, v in search.best_params_.items()},
                    "best_cv_f1_score": round(float(search.best_score_), 4),
                    "search_time_seconds": round(elapsed, 1),
                    "before_tuning": hasil_baseline,
                    "after_tuning": hasil_tuned,
                },
            },
            f, indent=2,
        )

    print("\nTraining selesai (pipeline final). Ringkasan performa model:")
    for r in results:
        print(
            f"  {r['model']:<20} acc={r['accuracy']:.4f}  prec={r['precision']:.4f}  "
            f"rec={r['recall']:.4f}  f1={r['f1_score']:.4f}  auc={r['roc_auc']:.4f}"
        )
    print(f"\nModel, encoders, scaler, dan metrics tersimpan di folder {MODEL_DIR}/")


if __name__ == "__main__":
    main()
