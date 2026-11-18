# Kigali Solar Radiation Predictor

## 1. Mission and problem

Nyaruka makes last-mile delivery in Kigali faster, cleaner and more affordable by connecting businesses and customers with e-bicycle riders, through USSD and mobile money so anyone can use it.
E-bicycles are only as efficiency as the energy that charges them, and solar output changes every day with the weather.
This model predicts Kigali's daily solar radiation (MJ/m²/day) from that day's weather, so that Nyaruka team can plan how many e-bicycles its solar charging can power.

## 2. Dataset

- **Source:** NASA POWER (Prediction Of Worldwide Energy Resources), NASA's free satellite-based weather and solar data service.
- **Download the original NASA data in one click:** [NASA POWER direct download (CSV)](https://power.larc.nasa.gov/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,T2M,T2M_MAX,T2M_MIN,T2MDEW,RH2M,PRECTOTCORR,WS2M,PS&community=AG&longitude=30.0619&latitude=-1.9441&start=20010101&end=20260830&format=CSV)
  - You do not need to search the NASA website or fill in any form. The link already contains every setting used for this project, so NASA sends back the same CSV file straight away.
  - Settings inside the link:
    - `temporal/daily/point`: in order to obtain one value per day for a single location.
    - `latitude=-1.9441&longitude=30.0619`: for the exact location of Kigali, Rwanda.
    - `start=20010101&end=20260830`: 1 January 2001 to 30 August 2026 this enough to be confident.
    - `community=AG`: the agriculture setting, which gives solar radiation in MJ/m²/day.
    - `format=CSV`: a CSV file that opens in Excel or pandas.
    - `parameters=...`: the 10 weather values downloaded:
      - `ALLSKY_SFC_SW_DWN`: solar radiation reaching the ground, with clouds which is our target
      - `CLRSKY_SFC_SW_DWN`: solar radiation on a cloud-free day
      - `T2M`, `T2M_MAX`, `T2M_MIN`: mean, maximum and minimum temperature
      - `T2MDEW`: dew point
      - `RH2M`: relative humidity
      - `PRECTOTCORR`: rain
      - `WS2M`: wind speed
      - `PS`: surface pressure
  - The file starts with an 18 line NASA text header between `-BEGIN HEADER-` and `-END HEADER-`. The data table comes after it, with the date given as `YEAR` and `DOY` (day of the year, 1–366). To load it in pandas, use `pd.read_csv(path, skiprows=18)`.
- **Dataset used to train the model which is cleaned and organized in a better way:** [solar_dataset.csv](https://github.com/igorntwari/linear_regression_model/blob/main/summative/API/solar_dataset.csv), then click **Download raw file to save it locally**.
  - It differs from the NASA download in three ways:
    1. Columns are renamed. For example, `ALLSKY_SFC_SW_DWN` became `solar_radiation_mj`.
    2. Missing values (`-999`) are removed.
    3. Engineered features are added: `temp_range_c`, `dryness_gap_c`, `month`, `quarter`, `season` and `rain_category`.
- **Location:** Kigali, Rwanda (latitude −1.9441, longitude 30.0619).
- **Period and size:** 2001-01-01 to 2026-08-30, 9,373 daily rows, no missing values. And the File is located at: `summative/API/solar_dataset.csv` the important note here is that the date is the index column.
- **Target:** `solar_radiation_mj`, all-sky surface solar radiation in MJ/m²/day divide by 3.6 for kWh/m²/day.
- **Model inputs 9, which needs to be  typed by the user:** max, min and mean temperature, dew point, relative humidity, rain, wind speed, clear-sky radiation and the month ranges between 1–12.
- **Engineered features:** `temp_range_c`, max − min; clear skies give large day–night swings, `dryness_gap_c` then the mean temperature − dew point; a small gap means humid, cloudy air, and the one-hot categorical features `month`, `season` which reflect Rwanda's two dry and two rainy seasons and `rain_category` (dry / light / moderate / heavy). `pressure_kpa` which is almost constant and `quarter` which  was redundant are not used.
- **Split:** chronological, so the model never sees the future: train 2001–2021 approximately 7,670 days, test 2022–2026 1,703 days. Hyperparameters were tuned with time-series cross-validation on the training years only.
- **Models compared (test MSE):** SGDRegressor our gradient descent 8.08, LinearRegression 8.09, RandomForest 8.17, DecisionTree 9.01. The SGDRegressor pipeline is saved as `summative/API/best_model.pkl` (test RMSE ≈ 2.8 MJ/m²/day, R² ≈ 0.45).
- **Limitation:** NASA's radiation and its weather values both come from NASA satellite and reanalysis products, so the model learns relationships inside one modelled system, not between independent ground sensors and a forecast. Unfortunately Kigali has very few ground solar sensors.the next step is to cross-check the results against other independent satellite radiation product.

## 3. Public API Swagger UI

https://kigali-solar-api.onrender.com/docs

Endpoints: `GET /info` (explains the API: purpose, data, model, the 9 inputs with their allowed ranges, and an example request), `GET /health` (checks the service is up and the model is loaded), `POST /predict` (9 weather values in, predicted radiation out), `POST /retrain` (upload a CSV of new days; the model is updated immediately), `GET /docs`.

## 4. Video demo

https://www.youtube.com/watch?v=xR_mqu4qYh4

## 5. Run the mobile app

1. Install Flutter and Android Studio with an Android emulator by following the official documentation https://docs.flutter.dev/get-started/install. Check with `flutter doctor`.
2. Open the app folder and install the packages:
   ```bash
   cd summative/FlutterApp
   flutter pub get
   ```
3. The app is already pointed at the deployed API: the default `apiBaseUrl` in `summative/FlutterApp/lib/api_service.dart` is `https://kigali-solar-api.onrender.com`. No change is needed unless you deploy under a different URL.
4. Start an emulator with `flutter emulators --launch <emulator_id>` or plug in an Android phone with USB debugging on.
5. Run the app:
   ```bash
   flutter run
   ```
6. Fill in the nine fields and tap **Predict**.

> **Note about our render free plan:** the API runs on Render's free plan, which sleeps when idle. The first request can take up to about a minute while the server wakes up; the app shows "Waking up the server, please wait…" during that time.

## How to run the notebook and the API locally

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 or above is installed by uv if needed.

```bash
cd summative
uv sync                                    # creates .venv with runtime + notebook packages

# Notebook which re-trains the models and rewrites API/best_model.pkl
cd linear_regression
uv run jupyter lab multivariate.ipynb      # or: uv run jupyter nbconvert --to notebook --execute --inplace multivariate.ipynb

# API
cd ../API
uv run uvicorn prediction:app --reload     # Swagger UI at http://127.0.0.1:8000/docs
```

To point the app at the local API without editing the code:
`flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000` for the Android emulator or `http://127.0.0.1:8000` if you want to run it on the iOS simulator.

`summative/API/requirements.txt` is generated from `uv.lock` for Render:
`uv export --format requirements.txt --no-hashes --no-dev -o API/requirements.txt` (run from `summative/`).
