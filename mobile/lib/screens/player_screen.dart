import 'dart:async';

import 'package:flutter/material.dart';
import '../core/api_client.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:just_audio/just_audio.dart';

import '../core/models.dart';
import '../core/providers.dart';

class PlayerScreen extends ConsumerStatefulWidget {
  const PlayerScreen({super.key, required this.audiobookId});
  final String audiobookId;

  @override
  ConsumerState<PlayerScreen> createState() => _PlayerScreenState();
}

class _PlayerScreenState extends ConsumerState<PlayerScreen> {
  late final AudioPlayer _player;
  Audiobook? _audiobook;
  String? _error;
  Timer? _pollTimer;
  int _currentChapter = 0;
  double _speed = 1.0;

  static const speeds = [0.75, 1.0, 1.25, 1.5, 2.0];

  @override
  void initState() {
    super.initState();
    _player = AudioPlayer();
    _load();
    ref.listenManual(pushMessageProvider, (_, msg) {
      msg.whenData((push) {
        if (push.audiobookId == widget.audiobookId) _load();
      });
    });
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final ab = await api.getAudiobook(widget.audiobookId);
      ref.read(libraryProvider.notifier).refreshItem(ab);
      setState(() => _audiobook = ab);
      if (ab.isReady && ab.chapters.isNotEmpty) {
        _pollTimer?.cancel();
        await _prepareWithResume(ab);
      } else if (ab.isGenerating) {
        _startPolling();
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _prepareWithResume(Audiobook ab) async {
    final api = ref.read(apiClientProvider);
    final progress = await api.getProgress(ab.id);
    final chapterIndex = progress.chapterPosition.clamp(0, ab.chapters.length - 1);
    await _playChapter(chapterIndex, initialSeekSeconds: progress.positionSeconds);
  }

  Future<void> _playChapter(int index, {int initialSeekSeconds = 0}) async {
    final ab = _audiobook;
    if (ab == null) return;
    final chapter = ab.chapters[index];
    if (chapter.audioUrl == null) return;
    setState(() => _currentChapter = index);
    try {
      await _player.setUrl(chapter.audioUrl!);
      await _player.setSpeed(_speed);
      if (initialSeekSeconds > 0) {
        await _player.seek(Duration(seconds: initialSeekSeconds));
      }
      await _player.play();
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not load audio. Try again.');
    }
    _player.playerStateStream.listen((state) {
      if (state.processingState == ProcessingState.completed) {
        _onChapterCompleted();
      }
    });
  }

  void _onChapterCompleted() {
    final ab = _audiobook;
    if (ab == null) return;
    if (_currentChapter + 1 < ab.chapters.length) {
      _playChapter(_currentChapter + 1);
    } else {
      ref.read(apiClientProvider).saveProgress(ab.id, 0, 0);
    }
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
  }

  Future<void> _savePosition() async {
    final ab = _audiobook;
    if (ab == null) return;
    ref.read(apiClientProvider).saveProgress(
          ab.id,
          _currentChapter,
          _player.position.inSeconds,
        );
  }

  void _setSpeed(double speed) {
    setState(() => _speed = speed);
    _player.setSpeed(speed);
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final ab = _audiobook;

    return Scaffold(
      appBar: AppBar(title: Text(ab?.title ?? 'Audiobook')),
      body: ab == null
          ? Center(
              child: _error != null
                  ? Text(_error!, style: TextStyle(color: theme.colorScheme.error))
                  : const CircularProgressIndicator(),
            )
          : ab.isGenerating
              ? _GeneratingView(status: ab.status)
              : ab.status == 'failed'
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(32),
                        child: Text(
                          ab.errorMessage ?? 'Generation failed. Please try again.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: theme.colorScheme.error),
                        ),
                      ),
                    )
                  : _readyView(context, ab),
    );
  }

  Widget _readyView(BuildContext context, Audiobook ab) {
    final theme = Theme.of(context);
    return Column(
      children: [
        StreamBuilder<Duration>(
          stream: _player.positionStream,
          builder: (context, snapshot) {
            final position = snapshot.data ?? Duration.zero;
            final duration = _player.duration ?? Duration.zero;
            return Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  Text(
                    ab.chapters.isEmpty ? '' : ab.chapters[_currentChapter].title,
                    textAlign: TextAlign.center,
                    style: theme.textTheme.titleMedium,
                  ),
                  const SizedBox(height: 12),
                  Slider(
                    value: duration.inMilliseconds == 0
                        ? 0
                        : position.inMilliseconds
                            .clamp(0, duration.inMilliseconds)
                            .toDouble(),
                    max: duration.inMilliseconds.toDouble(),
                    onChanged: (v) {
                      _player.seek(Duration(milliseconds: v.toInt()));
                      _savePosition();
                    },
                  ),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(_fmt(position)),
                      Text(_fmt(duration)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      IconButton(
                        icon: const Icon(Icons.skip_previous),
                        onPressed: _currentChapter > 0
                            ? () => _playChapter(_currentChapter - 1)
                            : null,
                      ),
                      StreamBuilder<bool>(
                        stream: _player.playingStream,
                        builder: (_, snap) => IconButton.filled(
                          iconSize: 48,
                          icon: Icon((snap.data ?? false) ? Icons.pause : Icons.play_arrow),
                          onPressed: () {
                            if (_player.playing) {
                              _player.pause();
                              _savePosition();
                            } else {
                              _player.play();
                            }
                          },
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.skip_next),
                        onPressed: _currentChapter + 1 < ab.chapters.length
                            ? () => _playChapter(_currentChapter + 1)
                            : null,
                      ),
                    ],
                  ),
                  Wrap(
                    spacing: 8,
                    children: [
                      for (final s in speeds)
                        ChoiceChip(
                          label: Text('${s}x'),
                          selected: _speed == s,
                          onSelected: (_) => _setSpeed(s),
                        ),
                    ],
                  ),
                ],
              ),
            );
          },
        ),
        Expanded(
          child: ListView.builder(
            itemCount: ab.chapters.length,
            itemBuilder: (context, i) {
              final ch = ab.chapters[i];
              return ListTile(
                leading: CircleAvatar(
                  child: Text('${i + 1}'),
                ),
                title: Text(ch.title),
                subtitle: ch.durationSeconds != null
                    ? Text(_fmt(Duration(seconds: ch.durationSeconds!)))
                    : null,
                trailing: i == _currentChapter
                    ? const Icon(Icons.graphic_eq)
                    : null,
                selected: i == _currentChapter,
                onTap: () => _playChapter(i),
              );
            },
          ),
        ),
      ],
    );
  }

  String _fmt(Duration d) =>
      '${d.inHours > 0 ? '${d.inHours}:' : ''}'
      '${(d.inMinutes % 60).toString().padLeft(2, '0')}:'
      '${(d.inSeconds % 60).toString().padLeft(2, '0')}';
}

class _GeneratingView extends StatelessWidget {
  const _GeneratingView({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 24),
            Text(
              'Generating your audiobook…',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Status: $status. You will get a push notification when it is ready.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}
