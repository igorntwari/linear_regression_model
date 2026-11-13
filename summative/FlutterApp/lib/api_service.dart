import 'dart:convert';

import 'package:http/http.dart' as http;

/// Base URL of the deployed FastAPI service on Render (no trailing slash).
/// For local testing it can be overridden at build time:
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000   (Android emulator)
///   flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000  (iOS simulator)
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'https://kigali-solar-api.onrender.com',
);

/// A free Render service sleeps when idle and can take about a minute to wake up.
const Duration apiTimeout = Duration(seconds: 90);

class Prediction {
  final double mjPerM2Day;
  final double kwhPerM2Day;
  const Prediction(this.mjPerM2Day, this.kwhPerM2Day);
}

/// An error the server explained to us (e.g. a 422 validation error).
class ApiException implements Exception {
  final String message;
  const ApiException(this.message);
  @override
  String toString() => message;
}

/// Sends the 9 weather values to POST /predict and returns the prediction.
/// Throws [ApiException] for validation/server errors; network errors and
/// timeouts propagate to the caller.
Future<Prediction> predictSolar(Map<String, num> inputs) async {
  final response = await http
      .post(
        Uri.parse('$apiBaseUrl/predict'),
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: jsonEncode(inputs),
      )
      .timeout(apiTimeout);

  final Object? body = _tryDecode(response.body);
  if (response.statusCode == 200 && body is Map) {
    return Prediction(
      (body['solar_radiation_mj_m2_day'] as num).toDouble(),
      (body['solar_radiation_kwh_m2_day'] as num).toDouble(),
    );
  }
  if (response.statusCode == 422 && body is Map) {
    throw ApiException(describeValidationErrors(body['detail']));
  }
  throw ApiException('Server error (HTTP ${response.statusCode}). Please try again.');
}

Object? _tryDecode(String text) {
  try {
    return jsonDecode(text);
  } on FormatException {
    return null;
  }
}

/// Friendly names and allowed ranges. Keep the ranges identical to RANGES in
/// summative/API/prediction.py.
const Map<String, (String, num, num)> fieldInfo = {
  'temp_max_c': ('Max temperature', 5, 40),
  'temp_min_c': ('Min temperature', 0, 30),
  'temp_mean_c': ('Mean temperature', 5, 35),
  'dew_point_c': ('Dew point', -5, 30),
  'humidity_pct': ('Humidity', 0, 100),
  'rain_mm': ('Rain', 0, 150),
  'wind_speed_ms': ('Wind speed', 0, 10),
  'clear_sky_radiation_mj': ('Clear-sky radiation', 5, 40),
  'month_num': ('Month', 1, 12),
};

/// Turns FastAPI's 422 "detail" list into readable lines, e.g.
/// "Humidity must be between 0 and 100".
String describeValidationErrors(Object? detail) {
  if (detail is! List) return detail?.toString() ?? 'Invalid input.';
  final lines = <String>[];
  for (final err in detail) {
    if (err is! Map) continue;
    final loc = (err['loc'] as List?) ?? const [];
    final key = loc.isNotEmpty ? loc.last.toString() : '';
    final info = fieldInfo[key];
    final name = info?.$1 ?? key;
    final type = err['type']?.toString() ?? '';
    final msg = (err['msg']?.toString() ?? 'Invalid value').replaceFirst('Value error, ', '');
    if (info != null && (type.startsWith('greater_than') || type.startsWith('less_than'))) {
      lines.add('$name must be between ${info.$2} and ${info.$3}');
    } else if (info != null && type == 'missing') {
      lines.add('$name is required');
    } else if (info != null && type == 'int_type') {
      lines.add('$name must be a whole number');
    } else if (info != null && type.endsWith('_type')) {
      lines.add('$name must be a number');
    } else {
      lines.add(msg); // e.g. "temp_min_c (30.0) cannot be greater than temp_max_c (25.0)."
    }
  }
  return lines.isEmpty ? 'Invalid input.' : lines.join('\n');
}
