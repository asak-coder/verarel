import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../controllers/auth_controller.dart';
import '../services/chat_client.dart';

final dioProvider = Provider<Dio>((ref) {
  return Dio(
    BaseOptions(
      baseUrl: 'https://api.aken.firm.in',
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 20),
      sendTimeout: const Duration(seconds: 20),
      headers: <String, dynamic>{
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    ),
  );
});

final authStateProvider = StateNotifierProvider<AuthController, AuthState>((ref) {
  return AuthController(ref.read(dioProvider));
});

final chatClientProvider = Provider<ChatClient>((ref) {
  return ChatClient(
    dio: ref.read(dioProvider),
    getAccessToken: () => ref.read(authStateProvider).accessToken,
  );
});
