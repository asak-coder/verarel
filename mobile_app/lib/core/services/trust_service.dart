import 'package:dio/dio.dart';

class TrustService {
  TrustService(this._dio);

  final Dio _dio;

  Future<TrustResult> loadTrust(int userId) async {
    final Response<dynamic> response = await _dio.get<dynamic>('/api/trust/$userId');

    final dynamic data = response.data;
    if (data is! Map<String, dynamic>) {
      throw StateError('Invalid trust response');
    }

    return TrustResult(
      score: _readInt(data['score']),
      status: data['tier']?.toString() ?? data['status']?.toString() ?? 'Unknown',
      verified: data['verified'] as bool? ?? false,
      cached: data['cached'] as bool? ?? false,
    );
  }

  int _readInt(dynamic value) => value is num ? value.toInt() : int.tryParse(value?.toString() ?? '') ?? 0;
}

class TrustResult {
  const TrustResult({
    required this.score,
    required this.status,
    required this.verified,
    required this.cached,
  });

  final int score;
  final String status;
  final bool verified;
  final bool cached;
}
