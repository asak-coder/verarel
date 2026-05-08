import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class MatchScreen extends StatelessWidget {
  const MatchScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final List<_MatchCardData> matches = <_MatchCardData>[
      _MatchCardData(
        name: 'Ari',
        age: 27,
        distance: '2 km away',
        compatibility: 92,
        trust: 'Verified',
      ),
      _MatchCardData(
        name: 'Mina',
        age: 25,
        distance: '5 km away',
        compatibility: 84,
        trust: 'Medium',
      ),
      _MatchCardData(
        name: 'Noah',
        age: 29,
        distance: '1 km away',
        compatibility: 78,
        trust: 'High',
      ),
    ];

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
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'Match Feed',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Swipe, review compatibility, and open chat when the spark is right.',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Colors.white70),
                ),
                const SizedBox(height: 20),
                Expanded(
                  child: ListView.separated(
                    itemCount: matches.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 14),
                    itemBuilder: (BuildContext context, int index) {
                      final _MatchCardData match = matches[index];
                      return _MatchCard(
                        match: match,
                        onOpenChat: () => context.go('/chat/${index + 1}'),
                        onOpenCompatibility: () => context.go('/compatibility/${index + 1}'),
                        onOpenDatePlan: () => context.go('/date-plan/${index + 1}'),
                        onOpenTrust: () => context.go('/trust/${index + 1}'),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MatchCardData {
  _MatchCardData({
    required this.name,
    required this.age,
    required this.distance,
    required this.compatibility,
    required this.trust,
  });

  final String name;
  final int age;
  final String distance;
  final int compatibility;
  final String trust;
}

class _MatchCard extends StatelessWidget {
  const _MatchCard({
    required this.match,
    required this.onOpenChat,
    required this.onOpenCompatibility,
    required this.onOpenDatePlan,
    required this.onOpenTrust,
  });

  final _MatchCardData match;
  final VoidCallback onOpenChat;
  final VoidCallback onOpenCompatibility;
  final VoidCallback onOpenDatePlan;
  final VoidCallback onOpenTrust;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFF7C3AED).withValues(alpha: 0.22),
                ),
                child: const Icon(Icons.person_rounded, color: Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      '${match.name}, ${match.age}',
                      style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 2),
                    Text(match.distance, style: const TextStyle(color: Colors.white70)),
                  ],
                ),
              ),
              _MiniBadge(text: '${match.compatibility}%'),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: <Widget>[
              _InfoPill(label: 'Trust', value: match.trust),
              const SizedBox(width: 8),
              _InfoPill(label: 'Score', value: '${match.compatibility}'),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: <Widget>[
              FilledButton(onPressed: onOpenChat, child: const Text('Chat')),
              OutlinedButton(onPressed: onOpenCompatibility, child: const Text('Compatibility')),
              OutlinedButton(onPressed: onOpenDatePlan, child: const Text('Plan Date')),
              TextButton(onPressed: onOpenTrust, child: const Text('Trust')),
            ],
          ),
        ],
      ),
    );
  }
}

class _MiniBadge extends StatelessWidget {
  const _MiniBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFF5D06B).withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(text, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
    );
  }
}

class _InfoPill extends StatelessWidget {
  const _InfoPill({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        '$label: $value',
        style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.w600),
      ),
    );
  }
}
