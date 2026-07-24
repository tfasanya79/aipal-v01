// ignore_for_file: depend_on_referenced_packages, use_super_parameters

import 'package:aipal/providers/app_state.dart';
import 'package:aipal/screens/home_shell.dart';
import 'package:aipal/screens/onboarding_screen.dart';
import 'package:aipal/screens/splash_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';

void _mockSecureStorage() {
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(
        const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
        (call) async => null,
      );
}

void _mockAudioPlayerChannels() {
  for (final name in [
    'xyz.luan/audioplayers.global',
    'xyz.luan/audioplayers',
  ]) {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(MethodChannel(name), (_) async => null);
  }
}

class _TestWebViewPlatform extends WebViewPlatform {
  @override
  PlatformWebViewController createPlatformWebViewController(
    PlatformWebViewControllerCreationParams params,
  ) {
    return _TestWebViewController(params);
  }

  @override
  PlatformWebViewWidget createPlatformWebViewWidget(
    PlatformWebViewWidgetCreationParams params,
  ) {
    return _TestWebViewWidget(params);
  }
}

class _TestWebViewController extends PlatformWebViewController {
  _TestWebViewController(PlatformWebViewControllerCreationParams params)
    : super.implementation(params);

  @override
  Future<void> loadHtmlString(String html, {String? baseUrl}) async {}

  @override
  Future<void> setPlatformNavigationDelegate(
    PlatformNavigationDelegate handler,
  ) async {}

  @override
  Future<void> setJavaScriptMode(JavaScriptMode javaScriptMode) async {}

  @override
  Future<void> setBackgroundColor(Color color) async {}
}

class _TestWebViewWidget extends PlatformWebViewWidget {
  _TestWebViewWidget(PlatformWebViewWidgetCreationParams params)
    : super.implementation(params);

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}

Widget _wrap(AppState state) {
  return ChangeNotifierProvider.value(
    value: state,
    child: const MaterialApp(home: SplashScreen()),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  WebViewPlatform.instance = _TestWebViewPlatform();
  _mockSecureStorage();
  _mockAudioPlayerChannels();

  test('loadStoredAuth sets authReady without blocking on network', () async {
    final state = AppState();
    expect(state.authReady, isFalse);
    await state.loadStoredAuth();
    expect(state.authReady, isTrue);
  });

  testWidgets('shows spinner while auth not ready', (tester) async {
    final state = AppState();
    await tester.pumpWidget(_wrap(state));
    expect(find.byType(WebViewWidget), findsOneWidget);
    expect(find.text('Email for magic link'), findsNothing);
  });

  testWidgets('routes to email onboarding when token null', (tester) async {
    final state = AppState()..authReady = true;
    await tester.pumpWidget(_wrap(state));
    await tester.pump();
    expect(find.text('Email for magic link'), findsOneWidget);
    expect(find.byType(OnboardingScreen), findsOneWidget);
  });

  testWidgets('routes home when token exists without profile names', (
    tester,
  ) async {
    final state = AppState()
      ..authReady = true
      ..token = 'fake-token'
      ..profile = {'email': 'user@example.com'};
    await tester.pumpWidget(_wrap(state));
    await tester.pump();
    expect(find.byType(HomeShell), findsOneWidget);
    expect(find.text('What should I call you?'), findsNothing);
    expect(find.text('Email for magic link'), findsNothing);
  });

  testWidgets('routes to home when profile complete', (tester) async {
    final state = AppState()
      ..authReady = true
      ..token = 'fake-token'
      ..profile = {'wake_name': 'Alex', 'display_name': 'Alex'};
    await tester.pumpWidget(_wrap(state));
    await tester.pump();
    expect(find.byType(HomeShell), findsOneWidget);
    expect(find.text('Companion'), findsOneWidget);
  });
}
