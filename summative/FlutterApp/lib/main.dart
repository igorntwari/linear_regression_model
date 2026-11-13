import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'api_service.dart';

void main() => runApp(const SolarApp());

class SolarApp extends StatelessWidget {
  const SolarApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Solar Predictor',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: Colors.orange, useMaterial3: true),
      home: const PredictionPage(),
    );
  }
}

/// One input field: API key, on-screen label, hint, and whether it must be an integer.
class _InputSpec {
  final String key;
  final String label;
  final String hint;
  final bool integer;
  const _InputSpec(this.key, this.label, this.hint, {this.integer = false});
}

const _inputs = <_InputSpec>[
  _InputSpec('temp_max_c', 'Max temperature (°C)', 'e.g. 26.5'),
  _InputSpec('temp_min_c', 'Min temperature (°C)', 'e.g. 15.2'),
  _InputSpec('temp_mean_c', 'Mean temperature (°C)', 'e.g. 20.1'),
  _InputSpec('dew_point_c', 'Dew point (°C)', 'e.g. 14.0'),
  _InputSpec('humidity_pct', 'Relative humidity (%)', 'e.g. 72'),
  _InputSpec('rain_mm', 'Rain (mm/day)', 'e.g. 1.5'),
  _InputSpec('wind_speed_ms', 'Wind speed (m/s)', 'e.g. 1.3'),
  _InputSpec('clear_sky_radiation_mj', 'Clear-sky radiation (MJ/m²/day)', 'e.g. 26.0'),
  _InputSpec('month_num', 'Month (1 to 12)', 'e.g. 7', integer: true),
];

class PredictionPage extends StatefulWidget {
  const PredictionPage({super.key});

  @override
  State<PredictionPage> createState() => _PredictionPageState();
}

class _PredictionPageState extends State<PredictionPage> {
  final _controllers = {for (final i in _inputs) i.key: TextEditingController()};
  bool _loading = false;
  String? _error;
  Prediction? _result;

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  /// Client-side checks: every field filled in and a valid number.
  /// Range checks are done by the API (422) so the app always matches the server.
  Map<String, num>? _readInputs(List<String> problems) {
    final values = <String, num>{};
    for (final spec in _inputs) {
      final text = _controllers[spec.key]!.text.trim().replaceAll(',', '.');
      final name = fieldInfo[spec.key]!.$1;
      if (text.isEmpty) {
        problems.add('$name is required');
        continue;
      }
      final num? value = spec.integer ? int.tryParse(text) : double.tryParse(text);
      if (value == null) {
        problems.add(spec.integer ? '$name must be a whole number' : '$name must be a number');
      } else {
        values[spec.key] = value;
      }
    }
    return problems.isEmpty ? values : null;
  }

  Future<void> _predict() async {
    FocusScope.of(context).unfocus();
    final problems = <String>[];
    final values = _readInputs(problems);
    if (values == null) {
      setState(() {
        _error = problems.join('\n');
        _result = null;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });
    try {
      final result = await predictSolar(values);
      setState(() => _result = result);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } on TimeoutException {
      setState(() => _error = 'The server did not answer in time. It may still be waking up; please try again.');
    } on SocketException {
      setState(() => _error = 'Cannot reach the server. Check your internet connection and the API URL.');
    } on http.ClientException catch (e) {
      setState(() => _error = 'Network error: ${e.message}');
    } catch (e) {
      setState(() => _error = 'Unexpected error: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Kigali Solar Forecast')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                "Enter a day's weather in Kigali to predict its solar radiation.",
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: 16),
              for (final spec in _inputs) ...[
                TextField(
                  key: ValueKey('field_${spec.key}'),
                  controller: _controllers[spec.key],
                  keyboardType: TextInputType.numberWithOptions(
                    decimal: !spec.integer,
                    signed: spec.key == 'dew_point_c',
                  ),
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: spec.label,
                    hintText: spec.hint,
                    border: const OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
                const SizedBox(height: 12),
              ],
              const SizedBox(height: 4),
              FilledButton(
                onPressed: _loading ? null : _predict,
                style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
                child: const Text('Predict'),
              ),
              const SizedBox(height: 16),
              _ResultArea(loading: _loading, error: _error, result: _result),
            ],
          ),
        ),
      ),
    );
  }
}

/// The single display area: loading message, error message or prediction.
class _ResultArea extends StatelessWidget {
  final bool loading;
  final String? error;
  final Prediction? result;
  const _ResultArea({required this.loading, this.error, this.result});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final Widget child;
    Color color = theme.colorScheme.surfaceContainerHighest;

    if (loading) {
      child = const Row(
        children: [
          SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
          SizedBox(width: 12),
          Expanded(child: Text('Waking up the server, please wait…')),
        ],
      );
    } else if (error != null) {
      color = theme.colorScheme.errorContainer;
      child = Text(error!, key: const ValueKey('error_text'),
          style: TextStyle(color: theme.colorScheme.onErrorContainer));
    } else if (result != null) {
      child = Column(
        key: const ValueKey('result_text'),
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Predicted solar radiation', style: theme.textTheme.titleSmall),
          const SizedBox(height: 6),
          Text('${result!.mjPerM2Day.toStringAsFixed(2)} MJ/m²/day',
              style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
          Text('${result!.kwhPerM2Day.toStringAsFixed(2)} kWh/m²/day', style: theme.textTheme.titleMedium),
        ],
      );
    } else {
      child = const Text('The prediction will appear here.');
    }

    return Container(
      constraints: const BoxConstraints(minHeight: 72),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(12)),
      child: child,
    );
  }
}
