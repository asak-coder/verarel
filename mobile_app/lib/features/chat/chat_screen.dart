import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../controllers/auth_controller.dart';
import '../../core/providers.dart';
import '../../core/services/chat_service.dart';
import 'message_bubble.dart';
import 'suggestion_bar.dart';

final chatControllerProvider =
    StateNotifierProvider.family<ChatController, ChatState, int>((ref, matchId) {
  return ChatController(
    chatService: ref.read(chatServiceProvider),
    authState: ref.read(authControllerProvider),
    matchId: matchId,
  )..loadInitialData();
});

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({
    super.key,
    required this.matchId,
  });

  final int matchId;

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _applySuggestion(String text) {
    _messageController.text = text;
    _messageController.selection = TextSelection.fromPosition(
      TextPosition(offset: text.length),
    );
  }

  Future<void> _send() async {
    await ref.read(chatControllerProvider(widget.matchId).notifier).sendMessage(
          _messageController.text,
        );
    _messageController.clear();

    if (_scrollController.hasClients) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scrollController.hasClients) {
          _scrollController.animateTo(
            _scrollController.position.maxScrollExtent,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOut,
          );
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ChatState state = ref.watch(chatControllerProvider(widget.matchId));
    final ChatController controller = ref.read(chatControllerProvider(widget.matchId).notifier);

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: <Color>[Color(0xFF050816), Color(0xFF111827), Color(0xFF0B1120)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: SafeArea(
          child: Column(
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                child: Row(
                  children: <Widget>[
                    IconButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      icon: const Icon(Icons.arrow_back_rounded),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Chat',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                            ),
                      ),
                    ),
                    IconButton(
                      onPressed: controller.refreshSuggestions,
                      icon: const Icon(Icons.auto_awesome_rounded),
                      tooltip: 'AI suggestions',
                    ),
                  ],
                ),
              ),
              SuggestionBar(
                matchId: widget.matchId,
                onSuggestionTap: _applySuggestion,
              ),
              const SizedBox(height: 8),
              Expanded(
                child: state.isLoadingSuggestions && state.messages.isEmpty
                    ? const Center(child: CircularProgressIndicator())
                    : ListView.builder(
                        controller: _scrollController,
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        itemCount: state.messages.length,
                        itemBuilder: (BuildContext context, int index) {
                          final ChatMessage message = state.messages[index];
                          return MessageBubble(
                            text: message.text,
                            isMine: message.isMine,
                            timeLabel: message.timeLabel,
                          );
                        },
                      ),
              ),
              if (state.errorMessage != null)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      state.errorMessage!,
                      style: const TextStyle(color: Color(0xFFFCA5A5)),
                    ),
                  ),
                ),
              Padding(
                padding: EdgeInsets.fromLTRB(
                  16,
                  8,
                  16,
                  16 + MediaQuery.of(context).viewInsets.bottom,
                ),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: TextField(
                        controller: _messageController,
                        minLines: 1,
                        maxLines: 5,
                        style: const TextStyle(color: Colors.white),
                        decoration: InputDecoration(
                          hintText: 'Write a message',
                          hintStyle: const TextStyle(color: Colors.white54),
                          filled: true,
                          fillColor: Colors.white.withValues(alpha: 0.06),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(18),
                            borderSide: BorderSide.none,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    FilledButton(
                      onPressed: state.isSending ? null : _send,
                      child: state.isSending
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.send_rounded),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class ChatController extends StateNotifier<ChatState> {
  ChatController({
    required this.chatService,
    required this.authState,
    required this.matchId,
  }) : super(const ChatState());

  final ChatService chatService;
  final AuthState authState;
  final int matchId;

  Future<void> loadInitialData() async {
    await refreshSuggestions();
  }

  Future<void> refreshSuggestions() async {
    if (state.isLoadingSuggestions) {
      return;
    }

    state = state.copyWith(isLoadingSuggestions: true, errorMessage: null);

    try {
      final int? userId = authState.userId;
      if (userId == null) {
        throw StateError('Sign in required');
      }
      final List<String> suggestions = await chatService.fetchSuggestions(
        matchId: matchId,
        userId: userId,
      );
      state = state.copyWith(
        suggestions: suggestions,
        isLoadingSuggestions: false,
        errorMessage: null,
      );
    } catch (error) {
      state = state.copyWith(
        isLoadingSuggestions: false,
        errorMessage: 'Unable to load suggestions right now.',
      );
    }
  }

  Future<void> sendMessage(String text) async {
    final String message = text.trim();
    if (message.isEmpty || state.isSending) {
      return;
    }

    state = state.copyWith(
      isSending: true,
      errorMessage: null,
      messages: <ChatMessage>[
        ...state.messages,
        ChatMessage(text: message, isMine: true, timeLabel: 'Now'),
      ],
    );

    try {
      final int? userId = authState.userId;
      if (userId == null) {
        throw StateError('Sign in required');
      }
      await chatService.sendMessage(
        matchId: matchId,
        userId: userId,
        message: message,
      );
      state = state.copyWith(isSending: false);
    } catch (error) {
      state = state.copyWith(
        isSending: false,
        errorMessage: 'Message send failed.',
      );
    }
  }
}

class ChatState {
  const ChatState({
    this.messages = const <ChatMessage>[],
    this.suggestions = const <String>[],
    this.isSending = false,
    this.isLoadingSuggestions = false,
    this.errorMessage,
  });

  final List<ChatMessage> messages;
  final List<String> suggestions;
  final bool isSending;
  final bool isLoadingSuggestions;
  final String? errorMessage;

  ChatState copyWith({
    List<ChatMessage>? messages,
    List<String>? suggestions,
    bool? isSending,
    bool? isLoadingSuggestions,
    Object? errorMessage = _sentinel,
  }) {
    return ChatState(
      messages: messages ?? this.messages,
      suggestions: suggestions ?? this.suggestions,
      isSending: isSending ?? this.isSending,
      isLoadingSuggestions: isLoadingSuggestions ?? this.isLoadingSuggestions,
      errorMessage: identical(errorMessage, _sentinel) ? this.errorMessage : errorMessage as String?,
    );
  }

  static const Object _sentinel = Object();
}

class ChatMessage {
  ChatMessage({
    required this.text,
    required this.isMine,
    required this.timeLabel,
  });

  final String text;
  final bool isMine;
  final String timeLabel;
}
