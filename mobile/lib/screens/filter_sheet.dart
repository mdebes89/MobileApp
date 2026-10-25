import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/config.dart';
import '../core/providers.dart';

Future<Filters?> showFilterSheet(BuildContext context, WidgetRef ref) {
  return showModalBottomSheet<Filters>(
    context: context,
    isScrollControlled: true,
    builder: (_) => const FilterSheet(),
  );
}

class FilterSheet extends ConsumerStatefulWidget {
  const FilterSheet({super.key});

  @override
  ConsumerState<FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends ConsumerState<FilterSheet> {
  @override
  Widget build(BuildContext context) {
    final filters = ref.watch(filtersProvider);
    final controller = ref.read(filtersProvider.notifier);
    final theme = Theme.of(context);

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Filters', style: theme.textTheme.titleLarge),
            const SizedBox(height: 16),
            Text('LENGTH', style: theme.textTheme.labelLarge),
            const SizedBox(height: 8),
            SegmentedButton<int>(
              segments: const [
                ButtonSegment(value: 10, label: Text('10 min')),
                ButtonSegment(value: 30, label: Text('30 min')),
                ButtonSegment(value: 60, label: Text('60 min')),
              ],
              selected: {filters.lengthMinutes},
              onSelectionChanged: (s) => controller.set(filters.copyWith(lengthMinutes: s.first)),
            ),
            const SizedBox(height: 16),
            Text('VOICE', style: theme.textTheme.labelLarge),
            const SizedBox(height: 8),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'male', label: Text('Male')),
                ButtonSegment(value: 'female', label: Text('Female')),
              ],
              selected: {filters.voice},
              onSelectionChanged: (s) => controller.set(filters.copyWith(voice: s.first)),
            ),
            const SizedBox(height: 16),
            Text('LANGUAGE', style: theme.textTheme.labelLarge),
            const SizedBox(height: 8),
            DropdownMenu<String>(
              initialSelection: filters.language,
              onSelected: (v) {
                if (v != null) controller.set(filters.copyWith(language: v));
              },
              dropdownMenuEntries: [
                for (final lang in AppConfig.languages)
                  DropdownMenuEntry(value: lang, label: AppConfig.languageNames[lang] ?? lang),
              ],
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => Navigator.of(context).pop(filters),
                child: const Text('Apply'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
