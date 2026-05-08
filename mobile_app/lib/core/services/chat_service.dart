import 'package:dio/dio.dart';

class ChatService {
  ChatService(this._dio);

  final Dio _dio;

  Future<List<String>> fetchSuggestions({
    required int matchId,
    required int userId,
  }) async {
    final Response<dynamic> response = await _dio.get<dynamic>(
      '/api/chat/suggestions/$matchId',
      queryParameters: <String, dynamic>{
        'user_id': userId,
      },
    );

    final dynamic data = response.data;
    if (data is Map<String, dynamic>) {
      final dynamic suggestionsJson = data['suggestions'];
      if (suggestionsJson is List) {
        return suggestionsJson.map((dynamic item) => item.toString()).toList(growable: false);
      }
    }

    throw StateError('Invalid chat suggestions response');
  }

  Future<void> sendMessage({
    required int matchId,
    required int userId,
    required String message,
  }) async {
    await _dio.post<dynamic>(
      '/chat/generate',
      data: <String, dynamic>{
        'user_id': userId,
        'match_id': matchId,
        'recent_messages': <Map<String, dynamic>>[
          <String, dynamic>{'role': 'user', 'content': message.trim()},
        ],
        'mode': 'reply',
      },
    );
  }
}
