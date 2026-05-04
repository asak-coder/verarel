import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'controllers/auth_controller.dart';
import 'screens/date_architect_screen.dart';
import 'screens/date_planner_screen.dart';
import 'screens/profile_studio_screen.dart';
import 'screens/secure_chat_screen.dart';
import 'screens/swipe_screen.dart';
import 'services/chat_client.dart';

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

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/swipe',
    refreshListenable: GoRouterRefreshStream(ref.read(authStateProvider.notifier).stream),
    routes: <RouteBase>[
      GoRoute(
        path: '/swipe',
        builder: (BuildContext context, GoRouterState state) {
          return const SwipeScreen();
        },
      ),
      GoRoute(
        path: '/profile-studio',
        builder: (BuildContext context, GoRouterState state) {
          return const ProfileStudioScreen();
        },
      ),
      GoRoute(
        path: '/date-architect/:targetUserId',
        builder: (BuildContext context, GoRouterState state) {
          final int targetUserId = int.tryParse(state.pathParameters['targetUserId'] ?? '') ?? 0;
          return DateArchitectScreen(targetUserId: targetUserId);
        },
      ),
      GoRoute(
        path: '/date-planner/:matchId',
        builder: (BuildContext context, GoRouterState state) {
          final int matchId = int.tryParse(state.pathParameters['matchId'] ?? '') ?? 0;
          return DatePlannerScreen(matchId: matchId);
        },
      ),
      GoRoute(
        path: '/secure-chat/:matchId/:userAId/:userBId',
        builder: (BuildContext context, GoRouterState state) {
          final int matchId = int.tryParse(state.pathParameters['matchId'] ?? '') ?? 0;
          final int userAId = int.tryParse(state.pathParameters['userAId'] ?? '') ?? 0;
          final int userBId = int.tryParse(state.pathParameters['userBId'] ?? '') ?? 0;
          return SecureChatScreen(
            matchId: matchId,
            userAId: userAId,
            userBId: userBId,
          );
        },
      ),
    ],
  );
});

void main() {
  runApp(const ProviderScope(child: AkenApp()));
}

class AkenApp extends ConsumerWidget {
  const AkenApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      debugShowCheckedModeBanner: false,
      title: 'Aken',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF6D5EF6)),
        useMaterial3: true,
        brightness: Brightness.dark,
      ),
      routerConfig: router,
    );
  }
}

class GoRouterRefreshStream extends ChangeNotifier {
  GoRouterRefreshStream(Stream<dynamic> stream) {
    _subscription = stream.asBroadcastStream().listen((dynamic _) {
      notifyListeners();
    });
  }

  final StreamSubscription<dynamic> _subscription;

  @override
  void dispose() {
    _subscription.cancel();
    super.dispose();
  }
}
