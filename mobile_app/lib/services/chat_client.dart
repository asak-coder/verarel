import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

class ChatClient {
  ChatClient({
    required Dio dio,
    required String? Function() getAccessToken,
  })  : _dio = dio,
        _getAccessToken = getAccessToken;

  final Dio _dio;
  final String? Function() _getAccessToken;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  final StreamController<Map<String, dynamic>> _messagesController =
      StreamController<Map<String, dynamic>>.broadcast();

  Stream<Map<String, dynamic>> get messages => _messagesController.stream;

  Future<void> connect(int matchId) async {
    await disconnect();

    final token = _getAccessToken();
    if (token == null || token.isEmpty) {
      throw StateError('Missing access token');
    }

    final uri = Uri.parse(
      '${_dio.options.baseUrl.replaceFirst(RegExp(r'^http'), 'ws')}/ws/$matchId?token=$token',
    );

    _channel = WebSocketChannel.connect(uri);
    _subscription = _channel!.stream.listen(
      (dynamic event) {
        final decoded = event is String ? jsonDecode(event) : event;
        if (decoded is Map<String, dynamic>) {
          _messagesController.add(decoded);
        }
      },
      onError: (_) => disconnect(),
      onDone: () => disconnect(),
      cancelOnError: true,
    );
  }

  Future<void> sendMessage({
    required int matchId,
    required String message,
  }) async {
    if (_channel == null) {
      await connect(matchId);
    }

    _channel?.sink.add(
      jsonEncode(<String, dynamic>{
        'message': message,
      }),
    );
  }

  Future<List<String>> fetchIcebreakers({
    required int userAId,
    required int userBId,
  }) async {
    final response = await _dio.post<dynamic>(
      '/chat/icebreakers',
      data: <String, dynamic>{
        'user_a_id': userAId,
        'user_b_id': userBId,
      },
    );
    final data = response.data;
    if (data is Map<String, dynamic>) {
      final icebreakers = data['icebreakers'];
      if (icebreakers is List) {
        return icebreakers.map((dynamic item) => item.toString()).toList(growable: false);
      }
    }
    throw StateError('Invalid icebreaker response');
  }

  Future<String> checkTone({
    required String draftMessage,
  }) async {
    final response = await _dio.post<dynamic>(
      '/chat/tone-check',
      data: <String, dynamic>{
        'draft_message': draftMessage,
      },
    );
    final data = response.data;
    if (data is Map<String, dynamic>) {
      final analysis = data['analysis'];
      if (analysis is String) {
        return analysis;
      }
    }
    throw StateError('Invalid tone check response');
  }

  Future<void> preloadMatchPreview({required int matchId}) async {
    // Touch the backend connection early so the chat screen feels instant.
    await connect(matchId);
  }

  Future<void> disconnect() async {
    await _subscription?.cancel();
    _subscription = null;
    await _channel?.sink.close();
    _channel = null;
  }

  void dispose() {
    _messagesController.close();
  }
}
