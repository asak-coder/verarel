import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'chat_screen.dart';

class SuggestionBar extends ConsumerWidget {
  const SuggestionBar({
    super.key,
    required this.matchId,
    required this.onSuggestionTap,
  });

  final int matchId;
  final ValueChanged<String> onSuggestionTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ChatState state = ref.watch(chatControllerProvider(matchId));

    if (state.isLoadingSuggestions && state.suggestions.isEmpty) {
      return const SizedBox(
        height: 52,
        child: Center(
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }

    final List<String> suggestions = state.suggestions;
    if (suggestions.isEmpty) {
      return const SizedBox.shrink();
    }

    return SizedBox(
      height: 52,
      child: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        scrollDirection: Axis.horizontal,
        itemCount: suggestions.length,
        separatorBuilder: (_, __) => const SizedBox(width: 10),
        itemBuilder: (BuildContext context, int index) {
          final String suggestion = suggestions[index];
          return ActionChip(
            label: Text(suggestion),
            onPressed: () => onSuggestionTap(suggestion),
            backgroundColor: Colors.white.withValues(alpha: 0.08),
            labelStyle: const TextStyle(color: Colors.white),
            side: const BorderSide(color: Colors.white12),
          );
        },
      ),
    );
  }
}
