import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:solar_predictor/api_service.dart';
import 'package:solar_predictor/main.dart';

void main() {
  testWidgets('shows a readable error when fields are missing or not numbers', (tester) async {
    await tester.pumpWidget(const SolarApp());
    expect(find.text('Predict'), findsOneWidget);

    await tester.enterText(find.byKey(const ValueKey('field_humidity_pct')), 'abc');
    await tester.ensureVisible(find.text('Predict'));
    await tester.tap(find.text('Predict'));
    await tester.pump();

    final error = tester.widget<Text>(find.byKey(const ValueKey('error_text'))).data!;
    expect(error, contains('Max temperature is required'));
    expect(error, contains('Humidity must be a number'));
  });

  test('turns a FastAPI 422 detail list into readable messages', () {
    final msg = describeValidationErrors([
      {'type': 'less_than_equal', 'loc': ['body', 'humidity_pct'], 'msg': 'Input should be <= 100'},
      {'type': 'value_error', 'loc': ['body'], 'msg': 'Value error, temp_min_c (30.0) cannot be greater than temp_max_c (25.0).'},
    ]);
    expect(msg, 'Humidity must be between 0 and 100\ntemp_min_c (30.0) cannot be greater than temp_max_c (25.0).');
  });
}
