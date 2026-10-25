import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:purchases_flutter/purchases_flutter.dart';

import 'config.dart';

/// RevenueCat-backed paywall service: Google Play Billing under the hood.
class PaywallService {
  Future<void> init() async {
    await Purchases.setLogLevel(LogLevel.warn);
    await Purchases.configure(
      PurchasesConfiguration(AppConfig.revenueCatApiKey),
    );
  }

  Future<List<StoreProduct>> fetchOfferings() async {
    try {
      final offerings = await Purchases.getOfferings();
      final packages = offerings.current?.availablePackages ?? [];
      return packages.map((p) => p.storeProduct).toList();
    } catch (_) {
      return [];
    }
  }

  Future<bool> purchase(StoreProduct product) async {
    try {
      final result = await Purchases.purchaseStoreProduct(product);
      return result.entitlements.all[AppConfig.entProductId]?.isActive ?? false;
    } on PlatformException catch (e) {
      final code = e.code;
      if (code.contains('cancel')) return false;
      rethrow;
    }
  }

  Future<void> restore() async {
    final info = await Purchases.restorePurchases();
    if (info.entitlements.all[AppConfig.entProductId]?.isActive != true) {
      throw Exception('No purchases to restore.');
    }
  }
}

final paywallServiceProvider = Provider<PaywallService>((_) => PaywallService());
