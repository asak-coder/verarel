import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthService {
  AuthService({
    required Dio dio,
    required FlutterSecureStorage storage,
  })  : _dio = dio,
        _storage = storage;

  final Dio _dio;
  final FlutterSecureStorage _storage;

  static const String _tokenKey = 'access_token';
  static const String _userIdKey = 'user_id';
  static const String _reliabilityTierKey = 'reliability_tier';
  static const String _reputationScoreKey = 'reputation_score';

  Future<String> login({
    required String email,
    required String password,
  }) async {
    final Response<dynamic> response = await _dio.post<dynamic>(
      '/api/auth/login',
      data: <String, dynamic>{
        'email': email.trim(),
        'password': password,
      },
    );
    return _persistAuth(response.data);
  }

  Future<String> signup({
    required String email,
    required String password,
    required String displayName,
  }) async {
    final Response<dynamic> response = await _dio.post<dynamic>(
      '/api/auth/signup',
      data: <String, dynamic>{
        'email': email.trim(),
        'password': password,
        'display_name': displayName.trim(),
      },
    );
    return _persistAuth(response.data);
  }

  Future<void> logout() async {
    await _storage.delete(key: _tokenKey);
    await _storage.delete(key: _userIdKey);
    await _storage.delete(key: _reliabilityTierKey);
    await _storage.delete(key: _reputationScoreKey);
  }

  Future<String?> loadToken() => _storage.read(key: _tokenKey);

  Future<int?> loadUserId() async {
    final String? raw = await _storage.read(key: _userIdKey);
    return int.tryParse(raw ?? '');
  }

  Future<String?> loadReliabilityTier() => _storage.read(key: _reliabilityTierKey);

  Future<int?> loadReputationScore() async {
    final String? raw = await _storage.read(key: _reputationScoreKey);
    return int.tryParse(raw ?? '');
  }

  String _persistAuth(dynamic data) {
    if (data is! Map<String, dynamic>) {
      throw StateError('Invalid auth response');
    }

    final String token = (data['access_token'] ?? data['token'])?.toString() ?? '';
    if (token.isEmpty) {
      throw StateError('Missing access token');
    }

    final int? userId = _readInt(data['user_id'] ?? data['id']);
    final String? tier = data['reliability_tier']?.toString();
    final int? reputationScore = _readInt(data['reputation_score']);

    _storage.write(key: _tokenKey, value: token);
    if (userId != null) {
      _storage.write(key: _userIdKey, value: userId.toString());
    }
    if (tier != null && tier.isNotEmpty) {
      _storage.write(key: _reliabilityTierKey, value: tier);
    }
    if (reputationScore != null) {
      _storage.write(key: _reputationScoreKey, value: reputationScore.toString());
    }

    return token;
  }

  int? _readInt(dynamic value) => value is num ? value.toInt() : int.tryParse(value?.toString() ?? '');
}
