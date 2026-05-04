import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>((ref) {
  return AuthController(ref.read(dioProvider));
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
    String? errorMessage,
  }) {
    return AuthState(
      isLoading: isLoading ?? this.isLoading,
      accessToken: accessToken ?? this.accessToken,
      userId: userId ?? this.userId,
      reliabilityTier: reliabilityTier ?? this.reliabilityTier,
      reputationScore: reputationScore ?? this.reputationScore,
      errorMessage: errorMessage,
    );
  }
}

class AuthController extends StateNotifier<AuthState> {
  AuthController(this._dio) : super(const AuthState());

  final Dio _dio;
  final StreamController<AuthState> _streamController =
      StreamController<AuthState>.broadcast();

  Stream<AuthState> get stream => _streamController.stream;

  String? get accessToken => state.accessToken;

  void _emit(AuthState nextState) {
    state = nextState;
    _streamController.add(nextState);
  }

  Future<void> signIn({
    required String email,
    required String password,
  }) async {
    _emit(state.copyWith(isLoading: true, errorMessage: null));

    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/auth/login',
        data: <String, dynamic>{
          'email': email,
          'password': password,
        },
      );

      final data = response.data ?? <String, dynamic>{};
      final token = data['access_token'] as String?;
      _emit(
        state.copyWith(
          isLoading: false,
          accessToken: token,
          errorMessage: token == null ? 'Login failed' : null,
        ),
      );
    } on DioException catch (error) {
      _emit(
        state.copyWith(
          isLoading: false,
          errorMessage: _readErrorMessage(error),
        ),
      );
    }
  }

  Future<void> submitLivenessSession({
    required int userId,
    required String sessionToken,
  }) async {
    try {
      await _dio.post<Map<String, dynamic>>(
        '/security/verify-liveness',
        data: <String, dynamic>{
          'user_id': userId,
          'session_token': sessionToken,
        },
      );
    } on DioException catch (error) {
      _emit(
        state.copyWith(
          errorMessage: _readErrorMessage(error),
        ),
      );
      rethrow;
    }
  }

  Future<void> signOut() async {
    _emit(const AuthState());
  }

  String _readErrorMessage(DioException error) {
    final responseData = error.response?.data;
    if (responseData is Map<String, dynamic>) {
      final detail = responseData['detail'];
      if (detail is String && detail.isNotEmpty) {
        return detail;
      }
    }
    return 'Unable to authenticate right now';
  }

  @override
  void dispose() {
    _streamController.close();
    super.dispose();
  }
}
