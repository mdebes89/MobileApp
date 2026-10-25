class Chapter {
  final int position;
  final String title;
  final String arcSection;
  final int? durationSeconds;
  final String? audioUrl;

  const Chapter({
    required this.position,
    required this.title,
    required this.arcSection,
    this.durationSeconds,
    this.audioUrl,
  });

  factory Chapter.fromJson(Map<String, dynamic> json) => Chapter(
        position: (json['position'] as num).toInt(),
        title: json['title'] as String? ?? '',
        arcSection: json['arc_section'] as String? ?? '',
        durationSeconds: (json['duration_seconds'] as num?)?.toInt(),
        audioUrl: json['audio_url'] as String?,
      );
}

class Audiobook {
  final String id;
  final String title;
  final String topic;
  final String normalizedTopic;
  final int lengthMinutes;
  final String voice;
  final String language;
  final String status; // queued | generating | ready | failed
  final String? errorMessage;
  final List<Chapter> chapters;
  final bool? cached;

  const Audiobook({
    required this.id,
    required this.title,
    required this.topic,
    required this.normalizedTopic,
    required this.lengthMinutes,
    required this.voice,
    required this.language,
    required this.status,
    this.errorMessage,
    this.chapters = const [],
    this.cached,
  });

  bool get isReady => status == 'ready';
  bool get isGenerating => status == 'queued' || status == 'generating';

  factory Audiobook.fromJson(Map<String, dynamic> json) => Audiobook(
        id: json['id'] as String,
        title: json['title'] as String? ?? '',
        topic: json['topic'] as String? ?? '',
        normalizedTopic: json['normalized_topic'] as String? ?? '',
        lengthMinutes: (json['length_minutes'] as num).toInt(),
        voice: json['voice'] as String? ?? 'male',
        language: json['language'] as String? ?? 'en',
        status: json['status'] as String? ?? 'queued',
        errorMessage: json['error_message'] as String?,
        chapters: ((json['chapters'] as List?) ?? [])
            .map((c) => Chapter.fromJson(c as Map<String, dynamic>))
            .toList(),
        cached: json['cached'] as bool?,
      );
}

class CatalogEntry {
  final String id;
  final String title;
  final String topic;
  final int lengthMinutes;
  final String voice;
  final String language;
  final int chapterCount;

  const CatalogEntry({
    required this.id,
    required this.title,
    required this.topic,
    required this.lengthMinutes,
    required this.voice,
    required this.language,
    required this.chapterCount,
  });

  factory CatalogEntry.fromJson(Map<String, dynamic> json) => CatalogEntry(
        id: json['id'] as String,
        title: json['title'] as String? ?? '',
        topic: json['topic'] as String? ?? '',
        lengthMinutes: (json['length_minutes'] as num).toInt(),
        voice: json['voice'] as String? ?? 'male',
        language: json['language'] as String? ?? 'en',
        chapterCount: (json['chapter_count'] as num?)?.toInt() ?? 0,
      );
}

class Entitlement {
  final bool active;
  final String? productId;
  final String? expiresAt;

  const Entitlement({required this.active, this.productId, this.expiresAt});

  factory Entitlement.fromJson(Map<String, dynamic> json) => Entitlement(
        active: json['active'] as bool? ?? false,
        productId: json['product_id'] as String?,
        expiresAt: json['expires_at'] as String?,
      );
}
