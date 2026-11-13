# Solar Predictor (Flutter app)

A single-page Android and iOS app for Nyaruka's operations team. You enter one day's weather in Kigali, tap **Predict**, and the app calls the `POST /predict` endpoint of the Kigali Solar Radiation API. It shows the expected solar radiation in MJ/m²/day and kWh/m²/day.

## Inputs

| Field | Unit |
|---|---|
| Max temperature | °C |
| Min temperature | °C |
| Mean temperature | °C |
| Dew point | °C |
| Relative humidity | % |
| Rain | mm/day |
| Wind speed | m/s |
| Clear-sky radiation | MJ/m²/day |
| Month | 1 to 12 |

Missing or non-numeric values are reported by the app before any request is sent. Out-of-range values are rejected by the API (HTTP 422), and the app shows the reason, for example "Humidity must be between 0 and 100". Network errors and timeouts are shown in the same result area.

## Run

```bash
flutter pub get
flutter run
```

The API address is the `apiBaseUrl` constant in `lib/api_service.dart`. To use a local API instead, pass it at build time:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000    # Android emulator
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000   # iOS simulator
```

The hosted API sleeps when idle, so the first prediction can take up to about a minute.

## Code

- `lib/api_service.dart`: the HTTP call to `/predict` and the conversion of 422 errors into readable messages.
- `lib/main.dart`: the input form and the result area.
- `test/widget_test.dart`: input-validation and error-message tests.
