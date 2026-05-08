import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'controllers/auth_controller.dart';
import 'core/providers.dart';
import 'features/auth/login_screen.dart';
import 'features/auth/signup_screen.dart';
import 'features/chat/chat_screen.dart';
import 'features/compatibility/compatibility_widget.dart';
import 'features/date_planner/date_plan_screen.dart';
import 'features/match/match_screen.dart';
import 'features/trust/verification_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final AuthController authController = ref.read(authControllerProvider.notifier);

  return GoRouter(
    initialLocation: authController.accessToken == null ? '/login' : '/match',
    refreshListenable: GoRouterRefreshStream(authController.stream),
    routes: <RouteBase>[
      GoRoute(
        path: '/login',
        builder: (BuildContext context, GoRouterState state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/signup',
        builder: (BuildContext context, GoRouterState state) => const SignupScreen(),
      ),
      GoRoute(
        path: '/match',
        builder: (BuildContext context, GoRouterState state) => const MatchScreen(),
      ),
      GoRoute(
        path: '/chat/:matchId',
        builder: (BuildContext context, GoRouterState state) {
          final int matchId = int.tryParse(state.pathParameters['matchId'] ?? '0') ?? 0;
          return ChatScreen(matchId: matchId);
        },
      ),
      GoRoute(
        path: '/compatibility/:matchId',
        builder: (BuildContext context, GoRouterState state) {
          final int matchId = int.tryParse(state.pathParameters['matchId'] ?? '0') ?? 0;
          return CompatibilityWidget(matchId: matchId);
        },
      ),
      GoRoute(
        path: '/trust/:userId',
        builder: (BuildContext context, GoRouterState state) {
          final int userId = int.tryParse(state.pathParameters['userId'] ?? '0') ?? 0;
          return VerificationScreen(userId: userId);
        },
      ),
      GoRoute(
        path: '/date-plan/:matchId',
        builder: (BuildContext context, GoRouterState state) {
          final int matchId = int.tryParse(state.pathParameters['matchId'] ?? '0') ?? 0;
          return DatePlanScreen(matchId: matchId);
        },
      ),
    ],
  );
});

void main() {
  runApp(const ProviderScope(child: VerarelApp()));
}

class VerarelApp extends ConsumerWidget {
  const VerarelApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final GoRouter router = ref.watch(routerProvider);

    return MaterialApp.router(
      debugShowCheckedModeBanner: false,
      title: 'verarel.com',
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF7C3AED),
          brightness: Brightness.dark,
        ),
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
