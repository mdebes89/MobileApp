import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';


import '../core/providers.dart';
import 'player_screen.dart';

class LibraryScreen extends ConsumerWidget {
  const LibraryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final library = ref.watch(libraryProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('My Library')),
      body: library.items.isEmpty
          ? Center(
              child: Text(
                'Audiobooks you request will appear here.',
                style: theme.textTheme.bodyLarge
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            )
          : ListView.builder(
              itemCount: library.items.length,
              itemBuilder: (context, i) {
                final ab = library.items[i];
                return Dismissible(
                  key: ValueKey(ab.id),
                  direction: DismissDirection.endToStart,
                  background: Container(
                    color: theme.colorScheme.errorContainer,
                    alignment: Alignment.centerRight,
                    padding: const EdgeInsets.only(right: 24),
                    child: Icon(Icons.delete, color: theme.colorScheme.onErrorContainer),
                  ),
                  onDismissed: (_) => ref.read(libraryProvider.notifier).remove(ab.id),
                  child: ListTile(
                    leading: Icon(
                      ab.isReady
                          ? Icons.play_circle
                          : ab.status == 'failed'
                              ? Icons.error
                              : Icons.hourglass_top,
                      color: ab.isReady ? theme.colorScheme.primary : null,
                    ),
                    title: Text(ab.title.isEmpty ? ab.topic : ab.title),
                    subtitle: Text(
                      '${ab.lengthMinutes} min · ${ab.voice} · ${ab.language.toUpperCase()} · ${ab.status}',
                    ),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => PlayerScreen(audiobookId: ab.id),
                      ),
                    ),
                  ),
                );
              },
            ),
    );
  }
}
