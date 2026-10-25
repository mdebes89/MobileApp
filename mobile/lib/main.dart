import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/config.dart';
import 'core/paywall.dart';
import 'core/providers.dart';
import 'screens/home_screen.dart';
import 'screens/library_screen.dart';
import 'screens/login_screen.dart';
import 'screens/paywall_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  try {
    await Firebase.initializeApp();
    FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);
  } catch (_) {
    // Firebase optional in dev; push disabled when not configured.
  }
  runApp(const ProviderScope(child: HistoryAudiobooksApp()));
}

class HistoryAudiobooksApp extends ConsumerStatefulWidget {
  const HistoryAudiobooksApp({super.key});

  @override
  ConsumerState<HistoryAudiobooksApp> createState() => _HistoryAudiobooksAppState();
}

class _HistoryAudiobooksAppState extends ConsumerState<HistoryAudiobooksApp> {
  @override
  void initState() {
    super.initState();
    _registerPush();
    _initBilling();
  }

  Future<void> _registerPush() async {
    try {
      final messaging = FirebaseMessaging.instance;
      await messaging.requestPermission();
      final token = await messaging.getToken();
      if (token != null) {
        if (ref.read(authProvider).isSignedIn) {
          await ref.read(apiClientProvider).registerDevice(token);
        }
        ref.listenManual(authProvider, (_, __) async {
          final t = await messaging.getToken();
          if (t != null && ref.read(authProvider).isSignedIn) {
            await ref.read(apiClientProvider).registerDevice(t);
          }
        });
      }
    } catch (_) {
      // push optional
    }
  }

  Future<void> _initBilling() async {
    try {
      if (AppConfig.revenueCatApiKey.isNotEmpty) {
        await ref.read(paywallServiceProvider).init();
      }
    } catch (_) {
      // billing optional in dev
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'History Audiobooks',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF6750A4)),
      ),
      home: ref.watch(authProvider).isSignedIn ? const Shell() : const LoginScreen(),
    );
  }
}

class Shell extends StatelessWidget {
  const Shell({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        body: const TabBarView(
          children: [
            HomeScreen(),
            LibraryScreen(),
          ],
        ),
        bottomNavigationBar: const TabBar(
          tabs: [
            Tab(icon: Icon(Icons.home), text: 'Home'),
            Tab(icon: Icon(Icons.library_music), text: 'Library'),
          ],
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const PaywallScreen()),
          ),
          icon: const Icon(Icons.workspace_premium),
          label: const Text('Premium'),
        ),
      ),
    );
  }
}
