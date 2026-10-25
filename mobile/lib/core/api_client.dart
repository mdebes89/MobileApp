import 'package:dio/dio.dart';

import 'config.dart';
import 'models.dart';

class ApiException implements Exception {
  final int? statusCode;
  final String message;
  ApiException(this.message, {this.statusCode});

  bool get isPaymentRequired => statusCode == 402;
  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({required this.idTokenProvider}) {
    _dio = Dio(BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
    ));
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await idTokenProvider();
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
    ));
  }

  final Future<String?> Function() idTokenProvider;
  late final Dio _dio;

  Future<Audiobook> createAudiobook({
    required String topic,
    required int lengthMinutes,
    required String voice,
    required String language,
    String? fcmToken,
  }) async {
    try {
      final res = await _dio.post(
        '/audiobooks',
        data: {
          'topic': topic,
          'length_minutes': lengthMinutes,
          'voice': voice,
          'language': language,
        },
        options: fcmToken == null
            ? null
            : Options(headers: {'X-Device-Token': fcmToken}),
      );
      return Audiobook.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw _wrap(e);
    }
  }

  Future<Audiobook> getAudiobook(String id) async {
    try {
      final res = await _dio.get('/audiobooks/$id');
      return Audiobook.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw _wrap(e);
    }
  }

  Future<List<CatalogEntry>> searchCatalog(String? topic) async {
    try {
      final res = await _dio.get('/audiobooks', queryParameters: {
        if (topic != null && topic.trim().isNotEmpty) 'topic': topic.trim(),
        'limit': 50,
      });
      final results = (res.data['results'] as List).cast<Map<String, dynamic>>();
      return results.map(CatalogEntry.fromJson).toList();
    } on DioException catch (e) {
      throw _wrap(e);
    }
  }

  Future<Entitlement> getEntitlement() async {
    try {
      final res = await _dio.get('/me/entitlement');
      return Entitlement.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw _wrap(e);
    }
  }

  Future<void> registerDevice(String fcmToken) async {
    try {
      await _dio.post('/me/device', data: {'fcm_token': fcmToken});
    } on DioException catch (e) {
      throw _wrap(e);
    }
  }

  Future<void> saveProgress(String audiobookId, int chapterPosition, int positionSeconds) async {
    try {
      await _dio.post(
        '/me/progress',
        queryParameters: {'audiobook_id': audiobookId},
        data: {'chapter_position': chapterPosition, 'position_seconds': positionSeconds},
      );
    } on DioException {
      // progress sync is best-effort
    }
  }

  Future<({int chapterPosition, int positionSeconds})> getProgress(String audiobookId) async {
    try {
      final res = await _dio.get('/me/progress', queryParameters: {'audiobook_id': audiobookId});
      final data = res.data as Map<String, dynamic>;
      return (
        chapterPosition: (data['chapter_position'] as num?)?.toInt() ?? 0,
        positionSeconds: (data['position_seconds'] as num?)?.toInt() ?? 0,
      );
    } on DioException {
      return (chapterPosition: 0, positionSeconds: 0);
    }
  }

  ApiException _wrap(DioException e) {
    final status = e.response?.statusCode;
    String message = 'Network error. Please try again.';
    if (e.response?.data is Map) {
      final detail = (e.response!.data as Map)['detail'];
      if (detail != null) message = detail.toString();
    } else if (status == 402) {
      message = 'Subscription required to generate new audiobooks.';
    } else if (status == 401) {
      message = 'Please sign in again.';
    }
    return ApiException(message, statusCode: status);
  }
}
