import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/models.dart';
import '../core/providers.dart';
import 'filter_sheet.dart';
import 'player_screen.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  final _searchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    ref.listenManual(pushMessageProvider, (_, msg) {
      msg.whenData((push) => _openAudiobook(push.audiobookId));
    });
  }

  Future<void> _openAudiobook(String id) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => PlayerScreen(audiobookId: id)),
    );
  }

  Future<void> _startGeneration() async {
    final topic = _searchController.text.trim();
    if (topic.isEmpty) return;
    final filters = await showFilterSheet(context, ref);
    if (filters == null || !mounted) return;

    final api = ref.read(apiClientProvider);
    final library = ref.read(libraryProvider.notifier);
    final scaffold = ScaffoldMessenger.of(context);
    try {
      final ab = await api.createAudiobook(
        topic: topic,
        lengthMinutes: filters.lengthMinutes,
        voice: filters.voice,
        language: filters.language,
      );
      await library.add(ab);
      if (ab.isReady) {
        scaffold.showSnackBar(
          SnackBar(content: Text('Already in the catalog: ${ab.title}')),
        );
      } else {
        scaffold.showSnackBar(
          const SnackBar(content: Text('Generating your audiobook…')),
        );
      }
      await _openAudiobook(ab.id);
    } on ApiException catch (e) {
      scaffold.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final catalog = ref.watch(catalogProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('History Audiobooks'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authProvider.notifier).signOut(),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _searchController,
                    onSubmitted: (_) => ref.read(catalogProvider.notifier).onQueryChanged(_searchController.text),
                    decoration: InputDecoration(
                      hintText: 'Enter a topic: bricks, coffee, paper…',
                      prefixIcon: const Icon(Icons.search),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: _startGeneration,
                  child: const Text('Generate'),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                TextButton.icon(
                  onPressed: () => ref.read(catalogProvider.notifier).onQueryChanged(_searchController.text),
                  icon: const Icon(Icons.tune),
                  label: const Text('Filters'),
                ),
              ],
            ),
          ),
          Expanded(
            child: catalog.loading && catalog.results.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : catalog.error != null && catalog.results.isEmpty
                    ? Center(child: Text(catalog.error!))
                    : catalog.results.isEmpty
                        ? Center(
                            child: Text(
                              'No audiobooks yet.\nGenerate the first one!',
                              textAlign: TextAlign.center,
                              style: theme.textTheme.bodyLarge?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          )
                        : RefreshIndicator(
                            onRefresh: () => ref.read(catalogProvider.notifier).search(null),
                            child: GridView.builder(
                              padding: const EdgeInsets.all(16),
                              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                                crossAxisCount: 2,
                                childAspectRatio: 0.9,
                                crossAxisSpacing: 12,
                                mainAxisSpacing: 12,
                              ),
                              itemCount: catalog.results.length,
                              itemBuilder: (context, i) =>
                                  _CatalogCard(entry: catalog.results[i], onTap: () => _openAudiobook(catalog.results[i].id)),
                            ),
                          ),
          ),
        ],
      ),
    );
  }
}

class _CatalogCard extends StatelessWidget {
  const _CatalogCard({required this.entry, required this.onTap});
  final CatalogEntry entry;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.auto_stories, size: 40, color: theme.colorScheme.primary),
              const Spacer(),
              Text(
                entry.title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleSmall,
              ),
              const SizedBox(height: 4),
              Text(
                entry.topic,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                children: [
                  _Chip('${entry.lengthMinutes} min'),
                  _Chip(entry.voice),
                  _Chip(entry.language.toUpperCase()),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip(this.label);
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.secondaryContainer,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label, style: Theme.of(context).textTheme.labelSmall),
    );
  }
}
