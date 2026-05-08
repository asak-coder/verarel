import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api/api_client.dart';
import 'services/auth_service.dart';
import 'services/chat_service.dart';
import 'services/compatibility_service.dart';
import 'services/date_plan_service.dart';
import 'services/trust_service.dart';

final secureStorageProvider = Provider<FlutterSecureStorage>((ref) {
  return const FlutterSecureStorage();
});

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(storage: ref.read(secureStorageProvider));
});

final dioProvider = Provider<Dio>((ref) {
  return ref.read(apiClientProvider).dio;
});

final authServiceProvider = Provider<AuthService>((ref) {
  return AuthService(
    dio: ref.read(dioProvider),
    storage: ref.read(secureStorageProvider),
  );
});

final chatServiceProvider = Provider<ChatService>((ref) {
  return ChatService(ref.read(dioProvider));
});

final compatibilityServiceProvider = Provider<CompatibilityService>((ref) {
  return CompatibilityService(ref.read(dioProvider));
});

final trustServiceProvider = Provider<TrustService>((ref) {
  return TrustService(ref.read(dioProvider));
});

final datePlanServiceProvider = Provider<DatePlanService>((ref) {
  return DatePlanService(ref.read(dioProvider));
});
