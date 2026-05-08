import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';

class SecureChatScreen extends ConsumerStatefulWidget {
  const SecureChatScreen({
    super.key,
    required this.matchId,
    required this.userAId,
    required this.userBId,
  });

  final int matchId;
  final int userAId;
  final int userBId;

  @override
  ConsumerState<SecureChatScreen> createState() => _SecureChatScreenState();
}

class _SecureChatScreenState extends ConsumerState<SecureChatScreen> {
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  StreamSubscription<Map<String, dynamic>>? _subscription;
  final List<_ChatItem> _items = <_ChatItem>[];
  final List<String> _suggestions = <String>[];
  bool _isFetchingIcebreakers = false;
  bool _isFetchingSuggestions = false;
  bool _isSending = false;
  String? _toneFeedback;

  @override
  void initState() {
    super.initState();
    final chatClient = ref.read(chatClientProvider);
    _subscription = chatClient.messages.listen((Map<String, dynamic> event) {
      if (!mounted) {
        return;
      }

      final String type = event['type']?.toString() ?? 'message';
      if (type == 'system_warning') {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(event['detail']?.toString() ?? 'Message flagged by moderation.'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        return;
      }

      setState(() {
        _items.add(
          _ChatItem(
            message: event['message']?.toString() ?? '',
            senderId: int.tryParse(event['sender_id']?.toString() ?? '') ?? 0,
            isMine: (int.tryParse(event['sender_id']?.toString() ?? '') ?? 0) ==
                (ref.read(authStateProvider).userId ?? 0),
          ),
        );
      });
      _scrollToBottom();
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(chatClientProvider).preloadMatchPreview(matchId: widget.matchId);
      _loadSuggestions();
    });
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _loadSuggestions() async {
    if (_isFetchingSuggestions) {
      return;
    }

    setState(() {
      _isFetchingSuggestions = true;
    });

    try {
      final authState = ref.read(authStateProvider);
      final userId = authState.userId;
      if (userId == null) {
        return;
      }

      final suggestions = await ref.read(chatClientProvider).fetchChatSuggestions(
            matchId: widget.matchId,
            userId: userId,
          );
      if (!mounted) {
        return;
      }

      setState(() {
        _suggestions
          ..clear()
          ..addAll(suggestions);
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
    } finally {
      if (mounted) {
        setState(() {
          _isFetchingSuggestions = false;
        });
      }
    }
  }

  void _applySuggestion(String suggestion) {
    _messageController.text = suggestion;
    _messageController.selection = TextSelection.fromPosition(
      TextPosition(offset: suggestion.length),
    );
  }

  Future<void> _sendMessage() async {
    final String draft = _messageController.text.trim();
    if (draft.isEmpty || _isSending) {
      return;
    }

    setState(() {
      _isSending = true;
    });

    try {
      await ref.read(chatClientProvider).sendMessage(
            matchId: widget.matchId,
            message: draft,
          );
      _messageController.clear();
      unawaited(_loadSuggestions());
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Unable to send message: $error'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isSending = false;
        });
      }
    }
  }

  Future<void> _toneCheck() async {
    final String draft = _messageController.text.trim();
    if (draft.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Type a message first.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    try {
      final String analysis = await ref.read(chatClientProvider).checkTone(draftMessage: draft);
      if (!mounted) {
        return;
      }
      setState(() {
        _toneFeedback = analysis;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(analysis),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Tone check failed: $error'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  Future<void> _showIcebreakers() async {
    if (_isFetchingIcebreakers) {
      return;
    }

    setState(() {
      _isFetchingIcebreakers = true;
    });

    try {
      final List<String> icebreakers = await ref.read(chatClientProvider).fetchIcebreakers(
            userAId: widget.userAId,
            userBId: widget.userBId,
          );
      if (!mounted) {
        return;
      }

      await showModalBottomSheet<void>(
        context: context,
        backgroundColor: const Color(0xFF0F172A),
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        builder: (BuildContext context) {
          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Icebreakers',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 12),
                  ...icebreakers.map(
                    (String icebreaker) => Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(16),
                        onTap: () {
                          _applySuggestion(icebreaker);
                          Navigator.of(context).pop();
                        },
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.06),
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: Colors.white12),
                          ),
                          child: Text(
                            icebreaker,
                            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                                  color: Colors.white,
                                ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Could not load icebreakers: $error'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isFetchingIcebreakers = false;
        });
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) {
        return;
      }
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authStateProvider);

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: <Color>[Color(0xFF050816), Color(0xFF0B1120), Color(0xFF111827)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: SafeArea(
          child: Column(
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                child: Row(
                  children: <Widget>[
                    IconButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      icon: const Icon(Icons.arrow_back_rounded),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Secure Chat',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                            ),
                      ),
                    ),
                    IconButton(
                      onPressed: _showIcebreakers,
                      icon: _isFetchingIcebreakers
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.casino_rounded),
                      tooltip: 'Icebreakers',
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Moderated in real time. Premium AI tools help you start and improve conversations.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.white70,
                        ),
                  ),
                ),
              ),
              if (_toneFeedback != null) ...<Widget>[
                const SizedBox(height: 10),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF7C3AED).withValues(alpha: 0.16),
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(color: const Color(0xFF7C3AED).withValues(alpha: 0.35)),
                      ),
                      child: Text(
                        _toneFeedback!,
                        style: const TextStyle(color: Colors.white),
                      ),
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 12),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Text(
                          'Smart Suggestions',
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                color: Colors.white,
                                fontWeight: FontWeight.w700,
                              ),
                        ),
                        const Spacer(),
                        TextButton(
                          onPressed: _isFetchingSuggestions ? null : _loadSuggestions,
                          child: _isFetchingSuggestions
                              ? const SizedBox(
                                  width: 14,
                                  height: 14,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Text('Refresh'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    if (_isFetchingSuggestions && _suggestions.isEmpty)
                      Column(
                        children: List<Widget>.generate(
                          3,
                          (int index) => Container(
                            width: double.infinity,
                            margin: const EdgeInsets.only(bottom: 10),
                            height: 44,
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.08),
                              borderRadius: BorderRadius.circular(16),
                            ),
                          ),
                        ),
                      )
                    else if (_suggestions.isEmpty)
                      Text(
                        'Suggestions will appear here automatically.',
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              color: Colors.white54,
                            ),
                      )
                    else
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: _suggestions
                            .map(
                              (String suggestion) => InkWell(
                                borderRadius: BorderRadius.circular(16),
                                onTap: () => _applySuggestion(suggestion),
                                child: Container(
                                  constraints: const BoxConstraints(minHeight: 44),
                                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                                  decoration: BoxDecoration(
                                    color: Colors.white.withValues(alpha: 0.08),
                                    borderRadius: BorderRadius.circular(16),
                                    border: Border.all(color: Colors.white12),
                                  ),
                                  child: Text(
                                    suggestion,
                                    style: const TextStyle(color: Colors.white, height: 1.25),
                                  ),
                                ),
                              ),
                            )
                            .toList(growable: false),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              Expanded(
                child: ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  itemCount: _items.length,
                  itemBuilder: (BuildContext context, int index) {
                    final item = _items[index];
                    return _MessageBubble(message: item.message, isMine: item.isMine);
                  },
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(
                  16,
                  8,
                  16,
                  16 + MediaQuery.of(context).viewInsets.bottom,
                ),
                child: Column(
                  children: <Widget>[
                    Row(
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
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 16,
                                vertical: 14,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Column(
                          children: <Widget>[
                            IconButton.filledTonal(
                              onPressed: _toneCheck,
                              icon: const Icon(Icons.psychology_alt_rounded),
                              tooltip: 'Tone Check',
                            ),
                            const SizedBox(height: 6),
                            IconButton.filled(
                              onPressed: _isSending ? null : _sendMessage,
                              icon: _isSending
                                  ? const SizedBox(
                                      width: 18,
                                      height: 18,
                                      child: CircularProgressIndicator(strokeWidth: 2),
                                    )
                                  : const Icon(Icons.send_rounded),
                              tooltip: 'Send',
                            ),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: _showIcebreakers,
                            icon: const Icon(Icons.casino_rounded),
                            label: const Text('Sparkle'),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: _toneCheck,
                            icon: const Icon(Icons.tune_rounded),
                            label: const Text('Tone Check'),
                          ),
                        ),
                      ],
                    ),
                    if (authState.accessToken == null) ...<Widget>[
                      const SizedBox(height: 8),
                      const Text(
                        'Sign in required for messaging.',
                        style: TextStyle(color: Colors.white54),
                      ),
                    ],
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

class _ChatItem {
  _ChatItem({
    required this.message,
    required this.senderId,
    required this.isMine,
  });

  final String message;
  final int senderId;
  final bool isMine;
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({
    required this.message,
    required this.isMine,
  });

  final String message;
  final bool isMine;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isMine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        constraints: const BoxConstraints(maxWidth: 300),
        decoration: BoxDecoration(
          color: isMine ? const Color(0xFF7C3AED) : Colors.white.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Text(
          message,
          style: const TextStyle(color: Colors.white, height: 1.3),
        ),
      ),
    );
  }
}
