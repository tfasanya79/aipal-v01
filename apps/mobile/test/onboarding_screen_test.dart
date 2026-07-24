import 'package:aipal/screens/onboarding_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('step 0 shows email field', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: OnboardingScreen()));
    expect(find.text('Email for magic link'), findsOneWidget);
    expect(find.text('Continue'), findsOneWidget);
  });

  testWidgets('empty email blocked on continue', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: OnboardingScreen()));
    await tester.tap(find.text('Continue'));
    await tester.pump();
    expect(find.text('Enter a valid email address'), findsOneWidget);
    expect(find.text('What should I call you?'), findsNothing);
  });

  testWidgets('invalid email without @ blocked', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: OnboardingScreen()));
    await tester.enterText(find.byType(TextField), 'notvalid');
    await tester.tap(find.text('Continue'));
    await tester.pump();
    expect(find.text('Enter a valid email address'), findsOneWidget);
  });

  testWidgets('valid email advances to profile step', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: OnboardingScreen()));
    await tester.enterText(find.byType(TextField), 'user@example.com');
    await tester.tap(find.text('Continue'));
    await tester.pump();
    expect(find.text('What should I call you?'), findsOneWidget);
    expect(find.text('Start with AiPal'), findsOneWidget);
    expect(find.text('Email for magic link'), findsNothing);
  });

  testWidgets('continueProfile skips email step', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: OnboardingScreen(continueProfile: true)),
    );
    expect(find.text('Email for magic link'), findsNothing);
    expect(find.text('What should I call you?'), findsOneWidget);
  });
}
