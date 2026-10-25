
import 'package:flutter_test/flutter_test.dart';

import 'package:history_audiobooks/core/models.dart';

void main() {
  test('Audiobook.fromJson parses chapters and status', () {
    final ab = Audiobook.fromJson({
      'id': 'abc',
      'title': 'Coffee',
      'topic': 'coffee',
      'normalized_topic': 'coffee',
      'length_minutes': 10,
      'voice': 'male',
      'language': 'en',
      'status': 'ready',
      'chapters': [
        {
          'position': 0,
          'title': 'The World Before Coffee',
          'arc_section': 'world_before',
          'duration_seconds': 291,
          'audio_url': 'https://example.com/a.mp3',
        },
      ],
    });
    expect(ab.isReady, isTrue);
    expect(ab.chapters, hasLength(1));
    expect(ab.chapters.first.arcSection, 'world_before');
    expect(ab.chapters.first.audioUrl, isNotNull);
  });

  test('generating states are recognized', () {
    final queued = Audiobook.fromJson({
      'id': 'x',
      'title': '',
      'topic': 't',
      'normalized_topic': 't',
      'length_minutes': 30,
      'voice': 'female',
      'language': 'fr',
      'status': 'queued',
    });
    expect(queued.isGenerating, isTrue);
    expect(queued.isReady, isFalse);
  });
}
