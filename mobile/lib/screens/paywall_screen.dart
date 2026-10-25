import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:purchases_flutter/purchases_flutter.dart';

import '../core/paywall.dart';
import '../core/providers.dart';

class PaywallScreen extends ConsumerStatefulWidget {
  const PaywallScreen({super.key});

  @override
  ConsumerState<PaywallScreen> createState() => _PaywallScreenState();
}

class _PaywallScreenState extends ConsumerState<PaywallScreen> {
  List<StoreProduct> _products = [];
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _busy = true);
    try {
      final products = await ref.read(paywallServiceProvider).fetchOfferings();
      setState(() => _products = products);
    } catch (e) {
      setState(() => _error = 'Could not load subscriptions: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _buy(StoreProduct product) async {
    setState(() => _busy = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final ok = await ref.read(paywallServiceProvider).purchase(product);
      if (ok) {
        await ref.read(entitlementProvider.notifier).refreshEntitlement();
        if (mounted) Navigator.of(context).pop(true);
      }
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Purchase failed: $e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _restore() async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(paywallServiceProvider).restore();
      await ref.read(entitlementProvider.notifier).refreshEntitlement();
      messenger.showSnackBar(const SnackBar(content: Text('Purchases restored.')));
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Subscribe')),
      body: _busy
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(24),
              children: [
                Icon(Icons.workspace_premium,
                    size: 72, color: theme.colorScheme.primary),
                const SizedBox(height: 16),
                Text(
                  'History Audiobooks Premium',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineSmall
                      ?.copyWith(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                Text(
                  'Generate unlimited AI-narrated history audiobooks. Streaming the shared catalog is always free.',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium
                      ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
                const SizedBox(height: 24),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Text(_error!,
                        style: TextStyle(color: theme.colorScheme.error)),
                  ),
                for (final product in _products)
                  Card(
                    child: ListTile(
                      title: Text(product.title),
                      subtitle: Text(product.description),
                      trailing: Text(product.priceString,
                          style: theme.textTheme.titleMedium),
                      onTap: () => _buy(product),
                    ),
                  ),
                const SizedBox(height: 16),
                OutlinedButton(
                  onPressed: _restore,
                  child: const Text('Restore purchases'),
                ),
              ],
            ),
    );
  }
}
