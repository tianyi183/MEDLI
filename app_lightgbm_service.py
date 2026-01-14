import glob
import io
import logging
import os
import zipfile
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
SERVER_MODEL_DIR = Path("17_models")
LOCAL_MODEL_DIR = BASE_DIR / "models"

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MODEL_DIR"] = (
    str(SERVER_MODEL_DIR) if SERVER_MODEL_DIR.exists() else str(LOCAL_MODEL_DIR)
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB limit
app.config["ALLOWED_EXTENSIONS"] = {"xlsx", "xls", "csv"}

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
logging.info("Upload folder ready at %s", app.config["UPLOAD_FOLDER"])


def allowed_file(filename: str) -> bool:
    """Return True if the filename extension is allowed."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def _prepare_results_frame(new_data: pd.DataFrame) -> pd.DataFrame:
    """Ensure we always have an ID column to anchor predictions."""
    if "eid" in new_data.columns:
        return pd.DataFrame({"eid": new_data["eid"].copy()})

    temp_ids = pd.Series(range(1, len(new_data) + 1), name="row_id")
    new_data["row_id"] = temp_ids
    return pd.DataFrame({"row_id": temp_ids})


def predict_with_models(filepath: str, user_dir: str):
    """
    Run every LightGBM model on the uploaded file and return (prediction_file, summary).
    """
    logging.info("Reading uploaded file: %s", filepath)
    if filepath.lower().endswith(".csv"):
        new_data = pd.read_csv(filepath)
    else:
        new_data = pd.read_excel(filepath)
    logging.info("File loaded successfully. Shape: %s", new_data.shape)

    model_files = glob.glob(os.path.join(app.config["MODEL_DIR"], "*.model"))
    logging.info("Discovered %d model files", len(model_files))
    if not model_files:
        raise FileNotFoundError("No LightGBM models were found in MODEL_DIR.")

    results = _prepare_results_frame(new_data)

    if "sex" in new_data.columns:
        new_data["sex"] = new_data["sex"].apply(
            lambda x: 1 if x in ("male", 1, "1") else 0
        )

    for model_file in model_files:
        model_name = Path(model_file).stem
        logging.info("Running model: %s", model_name)
        try:
            booster = lgb.Booster(model_file=model_file)
            feature_order = booster.feature_name()

            missing = set(feature_order) - set(new_data.columns)
            if missing:
                logging.warning(
                    "Model %s is missing %d features. Filling with zeros.",
                    model_name,
                    len(missing),
                )
                for feature in missing:
                    new_data[feature] = 0

            X_predict = new_data[feature_order]
            predictions = booster.predict(X_predict)
            results[model_name] = predictions
        except Exception as err:  # noqa: BLE001
            logging.exception("Model %s failed: %s", model_name, err)
            results[model_name] = None

    original_filename = os.path.basename(filepath)
    result_filename = f"predictions_{original_filename}"
    result_filepath = os.path.join(user_dir, result_filename)
    results.to_csv(result_filepath, index=False)
    logging.info("Prediction file stored at %s", result_filepath)

    summary = {
        col: results[col].mean()
        for col in results.columns
        if col not in {"eid", "row_id"} and pd.api.types.is_numeric_dtype(results[col])
    }
    return result_filepath, summary


@app.route("/api/login", methods=["POST"])
def login_api():
    """Handle file upload + LightGBM inference in one request."""
    if "file" not in request.files:
        return jsonify(success=False, error="No file part detected."), 400

    file = request.files["file"]
    username = request.form.get("username", "anonymous_user").strip()

    if not username or len(username) < 2:
        return jsonify(success=False, error="Username must be at least two characters."), 400

    if file.filename == "":
        return jsonify(success=False, error="No file selected."), 400

    if not allowed_file(file.filename):
        return jsonify(
            success=False,
            error="Only Excel (.xlsx/.xls) and CSV files are supported.",
        ), 400

    filename = secure_filename(file.filename)
    user_dir = os.path.join(app.config["UPLOAD_FOLDER"], username)
    os.makedirs(user_dir, exist_ok=True)
    logging.info("Upload directory ready at %s", user_dir)

    filepath = os.path.join(user_dir, filename)
    file.save(filepath)
    logging.info("Uploaded file saved to %s", filepath)

    try:
        result_filepath, prediction_summary = predict_with_models(filepath, user_dir)
    except Exception as err:  # noqa: BLE001
        logging.exception("Prediction failed for %s", filepath)
        return jsonify(success=False, error=f"Prediction failed: {err}"), 500

    return jsonify(
        success=True,
        message="File uploaded and predictions completed.",
        filename=filename,
        filepath=filepath,
        prediction_file=os.path.basename(result_filepath),
        prediction_summary=prediction_summary,
    )


@app.route("/api/download/<username>/<filename>", methods=["GET"])
def download_file(username, filename):
    """Download a single prediction artifact for a user."""
    user_dir = os.path.join(app.config["UPLOAD_FOLDER"], username)
    filepath = os.path.join(user_dir, filename)

    if not os.path.exists(filepath):
        return jsonify(success=False, error="Requested file does not exist."), 404

    return send_file(filepath, as_attachment=True, download_name=filename)


@app.route("/api/download-all/<username>", methods=["GET"])
def download_all_files(username):
    """Download all files for a user as a ZIP archive."""
    user_dir = os.path.join(app.config["UPLOAD_FOLDER"], username)
    if not os.path.exists(user_dir):
        return jsonify(success=False, error="User directory not found."), 404

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(user_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, start=user_dir)
                archive.write(file_path, arcname=os.path.join(username, arcname))

    memory_file.seek(0)
    return send_file(
        memory_file,
        as_attachment=True,
        download_name=f"{username}_files.zip",
        mimetype="application/zip",
    )


if __name__ == "__main__":
    if not Path(app.config["MODEL_DIR"]).exists():
        logging.warning("Model directory does not exist: %s", app.config["MODEL_DIR"])

    app.run(host="0.0.0.0", port=5000, debug=True)
