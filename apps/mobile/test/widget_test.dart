import 'package:aipal/main.dart';
import 'package:aipal/providers/app_state.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('App boots after auth ready', (tester) async {
    final appState = AppState()..authReady = true;
    await tester.pumpWidget(AipalApp(appState: appState));
    await tester.pump();
    expect(find.text('Email for magic link'), findsOneWidget);
  });
}
