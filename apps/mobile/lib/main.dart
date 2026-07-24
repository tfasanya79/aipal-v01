import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import 'providers/app_state.dart';
import 'screens/splash_screen.dart';
import 'services/notification_service.dart';
import 'services/wake_background_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    FlutterForegroundTask.initCommunicationPort();
    await WakeBackgroundService.init();
  }
  final appState = AppState();
  try {
    await NotificationService.instance.init(
      onForegroundNudge: (taskId, minutes) =>
          appState.handleForegroundNudge(taskId, minutes),
    );
  } catch (_) {
    // Notifications optional — must not block app launch (APK sideload / web).
  }
  await appState.loadStoredAuth();
  runApp(AipalApp(appState: appState));
  WidgetsBinding.instance.addPostFrameCallback((_) {
    unawaited(appState.finishBootstrap());
  });
}

class AipalApp extends StatelessWidget {
  const AipalApp({super.key, required this.appState});

  final AppState appState;

  @override
  Widget build(BuildContext context) {
    final app = MaterialApp(
      title: 'AiPal',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0D1117),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFFFC815),
          secondary: Color(0xFF003B2B),
          surface: Color(0xFF161B22),
        ),
        textTheme: GoogleFonts.nunitoTextTheme(ThemeData.dark().textTheme),
      ),
      home: const SplashScreen(),
    );
    return ChangeNotifierProvider.value(
      value: appState,
      child: (!kIsWeb && defaultTargetPlatform == TargetPlatform.android)
          ? WithForegroundTask(child: app)
          : app,
    );
  }
}
