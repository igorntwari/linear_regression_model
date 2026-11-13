"""Kigali daily solar radiation API (FastAPI).

Routes:
  POST /predict  - predict a day's solar radiation from 9 weather values
  POST /retrain  - upload a CSV of new days; the model is retrained immediately
  GET  /docs     - Swagger UI (auto-generated)

Run locally (from summative/API):  uvicorn prediction:app --reload
"""

from __future__ import annotations

import copy
import io
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sklearn.base import clone
from sklearn.linear_model import SGDRegressor
from sklearn.metrics import mean_squared_error

# Paths are relative to this file, never to the current working directory.
BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "best_model.pkl"
DATA_PATH = BASE_DIR / "solar_dataset.csv"

TARGET = "solar_radiation_mj"

# ---------------------------------------------------------------------------
# Feature engineering. MUST STAY IDENTICAL to add_derived and the lists in
# summative/linear_regression/multivariate.ipynb, otherwise the saved pipeline
# receives different columns from the ones it was trained on.
# ---------------------------------------------------------------------------
RAW_NUMERIC = ["temp_max_c", "temp_min_c", "temp_mean_c", "dew_point_c", "humidity_pct",
               "rain_mm", "wind_speed_ms", "clear_sky_radiation_mj"]
NUM_FEATURES = RAW_NUMERIC + ["temp_range_c", "dryness_gap_c"]
CAT_FEATURES = ["month", "season", "rain_category"]
FEATURES = NUM_FEATURES + CAT_FEATURES

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
SEASONS = ["DJF_short_dry", "MAM_long_rains", "JJA_long_dry", "SON_short_rains"]
RAIN_CATS = ["dry", "light", "moderate", "heavy"]


def add_derived(raw: pd.DataFrame) -> pd.DataFrame:
    # raw has the 8 RAW_NUMERIC columns plus month_num (1-12). Returns all FEATURES.
    out = raw.copy()
    out["temp_range_c"] = out["temp_max_c"] - out["temp_min_c"]
    out["dryness_gap_c"] = out["temp_mean_c"] - out["dew_point_c"]
    m = out["month_num"].astype(int)
    out["month"] = [MONTHS[i - 1] for i in m]
    out["season"] = np.select(
        [m.isin([12, 1, 2]), m.isin([3, 4, 5]), m.isin([6, 7, 8])],
        ["DJF_short_dry", "MAM_long_rains", "JJA_long_dry"], "SON_short_rains")
    out["rain_category"] = pd.cut(out["rain_mm"], [-np.inf, 1, 5, 15, np.inf],
                                  labels=RAIN_CATS).astype(str)
    return out
# ----------------------------- end of copied code ----------------------------

# Allowed input ranges, shared by /predict (Pydantic) and /retrain (CSV checks).
# Observed in solar_dataset.csv (2001-2026): temp_max 19.1-33.8, temp_min 8.5-19.4,
# temp_mean 14.9-25.3, dew point 4.9-18.0, humidity 39.5-93.8, rain 0-82.2,
# wind 0.37-2.65, clear-sky 16.6-28.9, target 3.9-27.9. Each range covers the data
# with a margin and stays physically realistic for Kigali.
RANGES: dict[str, tuple[float, float]] = {
    "temp_max_c": (5, 40),
    "temp_min_c": (0, 30),
    "temp_mean_c": (5, 35),
    "dew_point_c": (-5, 30),
    "humidity_pct": (0, 100),
    "rain_mm": (0, 150),
    "wind_speed_ms": (0, 10),
    "clear_sky_radiation_mj": (5, 40),
    "month_num": (1, 12),
}
TARGET_RANGE = (0.0, 40.0)  # MJ/m²/day; top-of-atmosphere at the equator is ~38

# ---------------------------------------------------------------------------
# Model state: one module-level pipeline, guarded by a lock.
# ---------------------------------------------------------------------------
_model_lock = threading.Lock()    # protects _model and _extra_rows_seen
_retrain_lock = threading.Lock()  # only one retraining job at a time
_model = None
_extra_rows_seen = 0  # rows added with partial_fit since the pipeline's preprocessing was fitted


def _load_model() -> None:
    global _model
    with _model_lock:
        _model = joblib.load(MODEL_PATH)


def _current_model():
    with _model_lock:
        if _model is None:
            raise HTTPException(status_code=503, detail="Model is not loaded yet.")
        return _model


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _load_model()
    yield


app = FastAPI(
    title="Kigali Solar Radiation API",
    description=(
        "Predicts Kigali's daily solar radiation (MJ/m²/day and kWh/m²/day) from that day's weather, "
        "so Nyaruka can plan how many e-bicycles its solar charging can power. "
        "Data: NASA POWER daily point data for Kigali, 2001-2026."
    ),
    version="1.0.0",
    lifespan=lifespan,
    redoc_url=None,                          # only /docs is exposed
    swagger_ui_oauth2_redirect_url=None,
)

# CORS. Browsers block a web page from calling an API on another origin unless the
# API allows that origin. Allowed: the service's own public URL, taken from the
# RENDER_EXTERNAL_URL environment variable that Render sets automatically (added only
# when it is set), and the local Flutter web debug servers on ports 5000 and 8080.
# Everything else is restricted: no "*" wildcard, so other websites cannot call the
# API from a visitor's browser, and with allow_credentials=True a wildcard would be
# unsafe anyway. Only GET, POST and OPTIONS (the preflight) are allowed, and only the
# Content-Type, Accept and Authorization headers. CORS is enforced by browsers only:
# the Flutter mobile app is not a browser, so CORS does not restrict it. This
# configuration controls which websites may call the API from a browser.
ALLOWED_ORIGINS = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
if RENDER_URL:
    ALLOWED_ORIGINS.insert(0, RENDER_URL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
    allow_credentials=True,
)


# The bare service URL sends people to the Swagger page. HEAD is listed explicitly
# because Render's health check sends HEAD /, which a plain GET route would not answer.
@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


# ---------------------------------------------------------------------------
# /predict
# ---------------------------------------------------------------------------
def _f(name: str, description: str, example):
    lo, hi = RANGES[name]
    return Field(..., ge=lo, le=hi, description=f"{description} Allowed range: {lo} to {hi}.",
                 examples=[example])


class WeatherInput(BaseModel):
    """One day of Kigali weather. All 9 fields are required."""

    # strict: "25" (a string) is rejected instead of being converted to 25.
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False, json_schema_extra={
        "example": {"temp_max_c": 26.5, "temp_min_c": 15.2, "temp_mean_c": 20.1, "dew_point_c": 14.0,
                    "humidity_pct": 72.0, "rain_mm": 1.5, "wind_speed_ms": 1.3,
                    "clear_sky_radiation_mj": 26.0, "month_num": 7}})

    temp_max_c: float = _f("temp_max_c", "Maximum air temperature at 2 m, °C.", 26.5)
    temp_min_c: float = _f("temp_min_c", "Minimum air temperature at 2 m, °C. Cannot exceed temp_max_c.", 15.2)
    temp_mean_c: float = _f("temp_mean_c", "Mean air temperature at 2 m, °C.", 20.1)
    dew_point_c: float = _f("dew_point_c", "Dew point temperature at 2 m, °C.", 14.0)
    humidity_pct: float = _f("humidity_pct", "Relative humidity at 2 m, %.", 72.0)
    rain_mm: float = _f("rain_mm", "Total rainfall for the day, mm.", 1.5)
    wind_speed_ms: float = _f("wind_speed_ms", "Mean wind speed at 2 m, m/s.", 1.3)
    clear_sky_radiation_mj: float = _f("clear_sky_radiation_mj",
                                       "Clear-sky solar radiation for the day (the cloud-free maximum), MJ/m²/day.", 26.0)
    month_num: int = _f("month_num", "Month of the year as an integer, 1 = January ... 12 = December.", 7)

    @model_validator(mode="after")
    def min_not_above_max(self):
        if self.temp_min_c > self.temp_max_c:
            raise ValueError(f"temp_min_c ({self.temp_min_c}) cannot be greater than temp_max_c ({self.temp_max_c}).")
        return self


class PredictionOut(BaseModel):
    solar_radiation_mj_m2_day: float = Field(description="Predicted solar radiation, MJ/m²/day.")
    solar_radiation_kwh_m2_day: float = Field(description="Same value in kWh/m²/day (MJ ÷ 3.6).")
    model: str = Field(description="Type of the model that made the prediction.")


@app.post("/predict", response_model=PredictionOut, summary="Predict daily solar radiation")
def predict(day: WeatherInput) -> PredictionOut:
    model = _current_model()
    X = add_derived(pd.DataFrame([day.model_dump()]))[FEATURES]
    # Radiation cannot be negative; a linear model could go below 0 at extreme inputs.
    mj = max(0.0, float(model.predict(X)[0]))
    return PredictionOut(solar_radiation_mj_m2_day=round(mj, 3),
                         solar_radiation_kwh_m2_day=round(mj / 3.6, 3),
                         model=type(model[-1]).__name__)


# ---------------------------------------------------------------------------
# /retrain
# ---------------------------------------------------------------------------
REQUIRED_COLUMNS = [TARGET] + RAW_NUMERIC  # plus the date in the first column
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PARTIAL_FIT_PASSES = 5


def _clean_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Coerce types, check ranges, and return the valid rows plus a count of dropped rows per reason."""
    dates = pd.to_datetime(df.iloc[:, 0], errors="coerce")
    data = df[REQUIRED_COLUMNS].apply(pd.to_numeric, errors="coerce")
    data["month_num"] = dates.dt.month
    data.index = dates

    reasons: dict[str, int] = {}
    bad = pd.Series(False, index=data.index)

    def flag(mask: pd.Series, reason: str):
        nonlocal bad
        new = mask & ~bad
        if new.any():
            reasons[reason] = int(new.sum())
        bad = bad | mask

    flag(pd.Series(dates.isna().to_numpy(), index=data.index),
         "date in the first column is missing or not a valid date")
    for col in REQUIRED_COLUMNS:
        flag(data[col].isna(), f"{col} is missing or not a number")
    for col, (lo, hi) in {**RANGES, TARGET: TARGET_RANGE}.items():
        if col == "month_num":
            continue
        flag((data[col] < lo) | (data[col] > hi), f"{col} outside {lo} to {hi}")
    flag(data["temp_min_c"] > data["temp_max_c"], "temp_min_c greater than temp_max_c")
    return data[~bad], reasons


def _base_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, index_col=0, parse_dates=True)
    data = df[REQUIRED_COLUMNS].copy()
    data["month_num"] = df.index.month
    return data


def _rows_fitted(pipe) -> int:
    """Number of rows the pipeline's preprocessing (and the model) was fitted on."""
    return int(pipe.named_steps["prep"].named_transformers_["num"].n_samples_seen_)


def _try_save(pipe) -> bool:
    # Render's free plan has an ephemeral filesystem: this file is lost when the service
    # restarts or redeploys, and the service then loads the original best_model.pkl from
    # the repo again. That is accepted for this project. If the disk is read-only we
    # keep serving the new model from memory and report saved_to_disk = false.
    try:
        tmp = MODEL_PATH.with_suffix(".pkl.tmp")
        joblib.dump(pipe, tmp, compress=3)
        os.replace(tmp, MODEL_PATH)
        return True
    except OSError:
        return False


@app.post("/retrain", summary="Upload a CSV of new days and retrain the model immediately")
def retrain(file: UploadFile = File(..., description=(
        "CSV with the same columns as solar_dataset.csv: the date (YYYY-MM-DD) in the first column, then "
        "solar_radiation_mj and the 8 weather inputs. Other columns are ignored and recomputed. "
        "Invalid rows are dropped and reported."))):
    global _model, _extra_rows_seen

    raw_bytes = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB.")
    if not raw_bytes.strip():
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as exc:  # malformed CSV, wrong encoding, binary file...
        raise HTTPException(status_code=400, detail=f"Could not read the file as CSV: {exc}") from exc
    if df.empty or df.shape[1] < 2:
        raise HTTPException(status_code=400, detail="The CSV has no data rows or only one column.")

    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(status_code=422, detail=(
            f"Missing required columns: {', '.join(missing)}. Expected the date as the first column, then "
            f"{', '.join(REQUIRED_COLUMNS)}."))

    new, dropped = _clean_rows(df)
    if new.empty:
        raise HTTPException(status_code=422, detail={
            "message": "No valid rows to train on; every row failed validation.",
            "rows_received": len(df), "dropped_rows_by_reason": dropped})

    with _retrain_lock:
        old = _current_model()
        X_new, y_new = add_derived(new)[FEATURES], new[TARGET]
        old_mse = float(mean_squared_error(y_new, old.predict(X_new)))

        if isinstance(old[-1], SGDRegressor):
            # Continue training the same model on the new rows only. The scaler and
            # encoder stay as they were fitted, so inputs are transformed exactly as before.
            method = "partial_fit"
            updated = copy.deepcopy(old)  # /predict keeps using `old` until the swap
            Xt = updated[:-1].transform(X_new)
            for _ in range(PARTIAL_FIT_PASSES):
                updated[-1].partial_fit(Xt, y_new.to_numpy())
            extra = _extra_rows_seen + len(new)
            total_rows = _rows_fitted(old) + extra
        else:
            # Tree, forest or LinearRegression: refit the whole pipeline (same hyperparameters)
            # on the original dataset plus the new rows. New rows replace original rows with the same date.
            method = "full refit"
            base = _base_dataset()
            base = base[~base.index.isin(new.index)]
            full = pd.concat([base, new])
            updated = clone(old).fit(add_derived(full)[FEATURES], full[TARGET])
            extra = 0
            total_rows = len(full)

        new_mse = float(mean_squared_error(y_new, updated.predict(X_new)))
        with _model_lock:  # swap: /predict uses the updated model from the next request on
            _model = updated
            _extra_rows_seen = extra
        saved = _try_save(updated)

    return {
        "method": method,
        "model": type(updated[-1]).__name__,
        "rows_received": int(len(df)),
        "rows_used": int(len(new)),
        "rows_dropped": int(len(df) - len(new)),
        "dropped_rows_by_reason": dropped,
        "total_training_rows": int(total_rows),
        "old_model_mse_on_new_rows": round(old_mse, 4),
        "new_model_mse_on_new_rows": round(new_mse, 4),
        "saved_to_disk": saved,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
