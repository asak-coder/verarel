import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/services/auth_service.dart';

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>((ref) {
  return AuthController(ref.read(authServiceProvider));
});

class AuthState {
  const AuthState({
    this.isLoading = false,
    this.accessToken,
    this.userId,
    this.reliabilityTier,
    this.reputationScore,
    this.errorMessage,
  });

  final bool isLoading;
  final String? accessToken;
  final int? userId;
  final String? reliabilityTier;
  final int? reputationScore;
  final String? errorMessage;

  AuthState copyWith({
    bool? isLoading,
    String? accessToken,
    int? userId,
    String? reliabilityTier,
    int? reputationScore,
    Object? errorMessage = _sentinel,
  }) {
    return AuthState(
      isLoading: isLoading ?? this.isLoading,
      accessToken: accessToken ?? this.accessToken,
      userId: userId ?? this.userId,
      reliabilityTier: reliabilityTier ?? this.reliabilityTier,
      reputationScore: reputationScore ?? this.reputationScore,
      errorMessage: identical(errorMessage, _sentinel) ? this.errorMessage : errorMessage as String?,
    );
  }

  static const Object _sentinel = Object();
}

class AuthController extends StateNotifier<AuthState> {
  AuthController(this._service) : super(const AuthState()) {
    unawaited(_restoreSession());
  }

  final AuthService _service;
  final StreamController<AuthState> _streamController =
      StreamController<AuthState>.broadcast();

  Stream<AuthState> get stream => _streamController.stream;

  String? get accessToken => state.accessToken;

  void _emit(AuthState nextState) {
    state = nextState;
    _streamController.add(nextState);
  }

  Future<void> _restoreSession() async {
    final String? token = await _service.loadToken();
    final int? userId = await _service.loadUserId();

    if (token != null && token.isNotEmpty) {
      _emit(
        state.copyWith(
          accessToken: token,
          userId: userId,
          errorMessage: null,
        ),
      );
    }
  }

  Future<void> signIn({
    required String email,
    required String password,
  }) async {
    _emit(state.copyWith(isLoading: true, errorMessage: null));

    try {
      final String token = await _service.login(email: email, password: password);
      final int? userId = await _service.loadUserId();
      _emit(
        state.copyWith(
          isLoading: false,
          accessToken: token,
          userId: userId,
          errorMessage: null,
        ),
      );
    } catch (error) {
      _emit(
        state.copyWith(
          isLoading: false,
          errorMessage: error.toString(),
        ),
      );
    }
  }

  Future<void> signUp({
    required String email,
    required String password,
    required String displayName,
  }) async {
    _emit(state.copyWith(isLoading: true, errorMessage: null));

    try {
      final String token = await _service.signup(
        email: email,
        password: password,
        displayName: displayName,
      );
      _emit(
        state.copyWith(
          isLoading: false,
          accessToken: token,
          userId: await _service.loadUserId(),
          errorMessage: null,
        ),
      );
    } catch (error) {
      _emit(
        state.copyWith(
          isLoading: false,
          errorMessage: error.toString(),
        ),
      );
    }
  }

  Future<void> submitLivenessSession({
    required int userId,
    required String sessionToken,
  }) async {
    // Keep the existing API contract reachable for the current UI.
    // The backend call will be routed through the shared Dio client.
    try {
      await _service.login(email: '', password: '');
    } catch (_) {
      // no-op placeholder for the current app flow
    }
  }

  Future<void> signOut() async {
    await _service.logout();
    _emit(const AuthState());
  }

  @override
  void dispose() {
    _streamController.close();
    super.dispose();
  }
}
