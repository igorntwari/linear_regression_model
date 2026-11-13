# Kigali Solar Radiation Predictor

## 1. Mission and problem

Nyaruka makes last-mile delivery in Kigali faster, cleaner and more affordable by connecting businesses and customers with e-bicycle riders, through USSD and mobile money so anyone can use it.
E-bicycles are only as clean as the energy that charges them, and solar output changes every day with the weather.
This model predicts Kigali's daily solar radiation (MJ/m²/day) from that day's weather, so Nyaruka can plan how many e-bicycles its solar charging can power.

## 2. Dataset

- **Source:** NASA POWER, https://power.larc.nasa.gov/ (daily point API, community `AG`).
- **Location:** Kigali, Rwanda (latitude −1.9441, longitude 30.0619).
- **Period and size:** 2001-01-01 to 2026-08-30, 9,373 daily rows, no missing values. File: `summative/API/solar_dataset.csv` (date is the index column).
- **Target:** `solar_radiation_mj`, all-sky surface solar radiation in MJ/m²/day (divide by 3.6 for kWh/m²/day).
- **Model inputs (9, typed by the user):** max, min and mean temperature, dew point, relative humidity, rain, wind speed, clear-sky radiation and the month (1–12).
- **Engineered features:** `temp_range_c` (max − min; clear skies give large day–night swings), `dryness_gap_c` (mean temperature − dew point; a small gap means humid, cloudy air), and the one-hot categorical features `month`, `season` (Rwanda's two dry and two rainy seasons) and `rain_category` (dry / light / moderate / heavy). `pressure_kpa` (almost constant) and `quarter` (redundant) are not used.
- **Split:** chronological, so the model never sees the future: train 2001–2021 (7,670 days), test 2022–2026 (1,703 days). Hyperparameters were tuned with time-series cross-validation on the training years only.
- **Models compared (test MSE):** SGDRegressor (gradient descent) 8.08, LinearRegression 8.09, RandomForest 8.17, DecisionTree 9.01. The SGDRegressor pipeline is saved as `summative/API/best_model.pkl` (test RMSE ≈ 2.8 MJ/m²/day, R² ≈ 0.45).
- **Limitation:** NASA's radiation and its weather values both come from NASA satellite and reanalysis products, so the model learns relationships inside one modelled system, not between independent ground sensors and a forecast. Africa has very few ground solar sensors. A possible next step is to cross-check the results against an independent satellite radiation product (Copernicus CAMS).

## 3. Public API (Swagger UI)

https://kigali-solar-api.onrender.com/docs

Endpoints: `POST /predict` (9 weather values in, predicted radiation out), `POST /retrain` (upload a CSV of new days; the model is updated immediately), `GET /docs`.

## 4. Video demo

https://www.youtube.com/watch?v=YOUR-VIDEO-ID

## 5. Run the mobile app

1. Install Flutter (stable channel) and Android Studio (with an Android emulator) by following https://docs.flutter.dev/get-started/install. Check with `flutter doctor`.
2. Open the app folder and install the packages:
   ```bash
   cd summative/FlutterApp
   flutter pub get
   ```
3. The app is already pointed at the deployed API: the default `apiBaseUrl` in `summative/FlutterApp/lib/api_service.dart` is `https://kigali-solar-api.onrender.com`. No change is needed unless you deploy under a different URL.
4. Start an emulator (`flutter emulators --launch <emulator_id>`) or plug in an Android phone with USB debugging on.
5. Run the app:
   ```bash
   flutter run
   ```
6. Fill in the nine fields and tap **Predict**.

> **Note:** the API runs on Render's free plan, which sleeps when idle. The first request can take up to about a minute while the server wakes up; the app shows "Waking up the server, please wait…" during that time.

## How to run the notebook and the API locally

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is installed by uv if needed.

```bash
cd summative
uv sync                                    # creates .venv with runtime + notebook packages

# Notebook (re-trains the models and rewrites API/best_model.pkl)
cd linear_regression
uv run jupyter lab multivariate.ipynb      # or: uv run jupyter nbconvert --to notebook --execute --inplace multivariate.ipynb

# API
cd ../API
uv run uvicorn prediction:app --reload     # Swagger UI at http://127.0.0.1:8000/docs
```

To point the app at the local API without editing the code:
`flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000` (Android emulator) or `http://127.0.0.1:8000` (iOS simulator).

`summative/API/requirements.txt` is generated from `uv.lock` for Render:
`uv export --format requirements.txt --no-hashes --no-dev -o API/requirements.txt` (run from `summative/`).
