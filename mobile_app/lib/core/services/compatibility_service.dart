import 'package:dio/dio.dart';

class CompatibilityService {
  CompatibilityService(this._dio);

  final Dio _dio;

  Future<CompatibilityResult> loadCompatibility(int matchId) async {
    final Response<dynamic> response = await _dio.get<dynamic>(
      '/api/compatibility/$matchId',
    );

    final dynamic data = response.data;
    if (data is! Map<String, dynamic>) {
      throw StateError('Invalid compatibility response');
    }

    final List<String> reasons = <String>[];
    final dynamic reasonsJson = data['reasons'];
    if (reasonsJson is List) {
      for (final dynamic item in reasonsJson) {
        reasons.add(item.toString());
      }
    }

    return CompatibilityResult(
      score: _readInt(data['score']),
      reasons: reasons,
      lastUpdated: data['last_updated']?.toString() ?? '',
      cacheHit: data['cache_hit'] as bool? ?? false,
    );
  }

  int _readInt(dynamic value) => value is num ? value.toInt() : int.tryParse(value?.toString() ?? '') ?? 0;
}

class CompatibilityResult {
  const CompatibilityResult({
    required this.score,
    required this.reasons,
    required this.lastUpdated,
    required this.cacheHit,
  });

  final int score;
  final List<String> reasons;
  final String lastUpdated;
  final bool cacheHit;
}
