import 'dart:async';


import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';
import 'config.dart';
import 'models.dart';

/// Background message handler must be a top-level function.
@pragma('vm:entry-point')
Future<void> firebaseBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
}

class AuthState {
  final GoogleSignInAccount? account;
  final String? idToken;
  final bool loading;
  final String? error;

  const AuthState({this.account, this.idToken, this.loading = false, this.error});

  bool get isSignedIn => account != null && idToken != null;

  AuthState copyWith({GoogleSignInAccount? account, String? idToken, bool? loading, String? error, bool clearError = false}) =>
      AuthState(
        account: account ?? this.account,
        idToken: idToken ?? this.idToken,
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
      );
}

class AuthController extends Notifier<AuthState> {
  GoogleSignIn? _googleSignIn;

  GoogleSignIn get _signIn => _googleSignIn ??= GoogleSignIn(
        serverClientId: AppConfig.googleServerClientId,
        scopes: ['openid', 'email', 'profile'],
      );

  @override
  AuthState build() {
    _maybeRestoreSession();
    return const AuthState(loading: true);
  }

  Future<void> _maybeRestoreSession() async {
    try {
      final account = await _signIn.signInSilently();
      if (account != null) {
        final auth = await account.authentication;
        state = state.copyWith(account: account, idToken: auth.idToken, loading: false);
      } else {
        state = state.copyWith(loading: false);
      }
    } catch (_) {
      state = state.copyWith(loading: false);
    }
  }

  Future<void> signIn() async {
    state = state.copyWith(loading: true, error: null);
    try {
      final account = await _signIn.signIn();
      if (account == null) {
        state = state.copyWith(loading: false);
        return;
      }
      final auth = await account.authentication;
      state = state.copyWith(account: account, idToken: auth.idToken, loading: false);
    } catch (e) {
      state = state.copyWith(
        loading: false,
        error: 'Google Sign-In failed: ${e.toString()}',
      );
    }
  }

  Future<void> signOut() async {
    await _signIn.signOut();
    state = const AuthState();
  }

  Future<String?> currentIdToken() => Future.value(state.idToken);
}

final authProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);

final apiClientProvider = Provider<ApiClient>((ref) {
  final auth = ref.watch(authProvider);
  return ApiClient(idTokenProvider: () async => auth.idToken);
});

class EntitlementState {
  final bool? active;
  final bool loading;
  final String? error;
  const EntitlementState({this.active, this.loading = false, this.error});

  bool get hasEntitlement => active == true;
}

class EntitlementController extends AutoDisposeAsyncNotifier<EntitlementState> {
  @override
  Future<EntitlementState> build() async {
    final api = ref.watch(apiClientProvider);
    try {
      final ent = await api.getEntitlement();
      return EntitlementState(active: ent.active);
    } on ApiException catch (e) {
      if (e.isUnauthorized) return const EntitlementState(active: false);
      return EntitlementState(active: false, error: e.message);
    }
  }

  Future<void> refreshEntitlement() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(build);
  }
}

final entitlementProvider =
    AutoDisposeAsyncNotifierProvider<EntitlementController, EntitlementState>(
        EntitlementController.new);

/// Catalog search state.
class CatalogState {
  final List<CatalogEntry> results;
  final bool loading;
  final String? error;
  const CatalogState({this.results = const [], this.loading = false, this.error});
}

class CatalogController extends AutoDisposeNotifier<CatalogState> {
  @override
  CatalogState build() {
    search(null);
    return const CatalogState(loading: true);
  }

  Timer? _debounce;

  void onQueryChanged(String query) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => search(query));
  }

  Future<void> search(String? topic) async {
    state = CatalogState(results: state.results, loading: true);
    final api = ref.read(apiClientProvider);
    try {
      final results = await api.searchCatalog(topic);
      state = CatalogState(results: results);
    } on ApiException catch (e) {
      state = CatalogState(results: state.results, error: e.message);
    }
  }
}

final catalogProvider =
    AutoDisposeNotifierProvider<CatalogController, CatalogState>(CatalogController.new);

/// Filters selected on the filter sheet.
class Filters {
  final int lengthMinutes;
  final String voice;
  final String language;

  const Filters({this.lengthMinutes = 10, this.voice = 'male', this.language = 'en'});

  Filters copyWith({int? lengthMinutes, String? voice, String? language}) => Filters(
        lengthMinutes: lengthMinutes ?? this.lengthMinutes,
        voice: voice ?? this.voice,
        language: language ?? this.language,
      );
}

class FiltersController extends Notifier<Filters> {
  static const _prefsKey = 'filters';

  @override
  Filters build() {
    _load();
    return const Filters();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    state = Filters(
      lengthMinutes: prefs.getInt('$_prefsKey.length') ?? 10,
      voice: prefs.getString('$_prefsKey.voice') ?? 'male',
      language: prefs.getString('$_prefsKey.language') ?? 'en',
    );
  }

  Future<void> set(Filters f) async {
    state = f;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('$_prefsKey.length', f.lengthMinutes);
    await prefs.setString('$_prefsKey.voice', f.voice);
    await prefs.setString('$_prefsKey.language', f.language);
  }
}

final filtersProvider = NotifierProvider<FiltersController, Filters>(FiltersController.new);

/// Library: audiobooks requested by this user (persisted locally, refreshed from server).
class LibraryState {
  final List<Audiobook> items;
  const LibraryState({this.items = const []});
}

class LibraryController extends Notifier<LibraryState> {
  static const _prefsKey = 'library_ids';

  @override
  LibraryState build() {
    _load();
    return const LibraryState();
  }

  Future<List<String>> _ids() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getStringList(_prefsKey) ?? [];
  }

  Future<void> _saveIds(List<String> ids) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_prefsKey, ids);
  }

  Future<void> _load() async {
    final api = ref.read(apiClientProvider);
    final ids = await _ids();
    final items = <Audiobook>[];
    for (final id in ids) {
      try {
        items.add(await api.getAudiobook(id));
      } on ApiException {
        // skip items that no longer exist
      }
    }
    state = LibraryState(items: items);
  }

  Future<void> add(Audiobook ab) async {
    final ids = await _ids();
    if (!ids.contains(ab.id)) {
      await _saveIds([ab.id, ...ids]);
    }
    final items = [
      ab,
      ...state.items.where((e) => e.id != ab.id),
    ];
    state = LibraryState(items: items);
  }

  Future<void> refreshItem(Audiobook ab) async {
    final items = state.items.map((e) => e.id == ab.id ? ab : e).toList();
    state = LibraryState(items: items);
  }

  Future<void> remove(String id) async {
    await _saveIds((await _ids()).where((e) => e != id).toList());
    state = LibraryState(items: state.items.where((e) => e.id != id).toList());
  }
}

final libraryProvider = NotifierProvider<LibraryController, LibraryState>(LibraryController.new);

/// FCM push: navigate-to-player on "audiobook_ready".
class PushMessage {
  final String audiobookId;
  PushMessage(this.audiobookId);
}

final pushMessageProvider = StreamProvider.autoDispose<PushMessage>((ref) {
  final controller = StreamController<PushMessage>.broadcast();
  try {
    FirebaseMessaging.onMessage.listen((message) {
      final id = message.data['audiobook_id'] as String?;
      if (id != null) controller.add(PushMessage(id));
    });
    FirebaseMessaging.onMessageOpenedApp.listen((message) {
      final id = message.data['audiobook_id'] as String?;
      if (id != null) controller.add(PushMessage(id));
    });
  } catch (e) {
    if (kDebugMode) debugPrint('FCM unavailable: $e');
  }
  ref.onDispose(controller.close);
  return controller.stream;
});
