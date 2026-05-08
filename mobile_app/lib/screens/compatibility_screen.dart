import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';

class CompatibilityScreen extends ConsumerStatefulWidget {
  const CompatibilityScreen({
    super.key,
    required this.matchId,
  });

  final int matchId;

  @override
  ConsumerState<CompatibilityScreen> createState() => _CompatibilityScreenState();
}

class _CompatibilityScreenState extends ConsumerState<CompatibilityScreen> {
  bool _isLoading = true;
  String? _errorMessage;
  CompatibilityData? _compatibility;

  @override
  void initState() {
    super.initState();
    _loadCompatibility();
  }

  Future<void> _loadCompatibility({bool silent = false}) async {
    if (!silent) {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
      });
    }

    try {
      final String? token = ref.read(authStateProvider).accessToken;
      if (token == null || token.isEmpty) {
        throw StateError('Sign in required');
      }

      final Response<dynamic> response = await ref.read(dioProvider).get<dynamic>(
            '/api/compatibility/${widget.matchId}',
            options: Options(
              headers: <String, dynamic>{
                'Authorization': 'Bearer $token',
              },
            ),
          );

      final data = response.data;
      if (data is! Map<String, dynamic>) {
        throw StateError('Invalid compatibility response');
      }

      _compatibility = CompatibilityData.fromJson(data);
      setState(() {
        _isLoading = false;
      });
    } catch (_) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Unable to load compatibility right now.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final CompatibilityData? compatibility = _compatibility;

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
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    IconButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      icon: const Icon(Icons.arrow_back_rounded),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Compatibility',
                        style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                            ),
                      ),
                    ),
                    IconButton(
                      onPressed: _isLoading ? null : () => _loadCompatibility(silent: true),
                      icon: const Icon(Icons.refresh_rounded),
                      tooltip: 'Refresh',
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  'Fast cached compatibility scoring with explainable match reasons.',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: Colors.white70,
                        height: 1.35,
                      ),
                ),
                const SizedBox(height: 20),
                if (_isLoading)
                  const Expanded(child: _CompatibilitySkeleton())
                else if (_errorMessage != null)
                  Expanded(
                    child: _CompatibilityError(
                      message: _errorMessage!,
                      onRetry: _loadCompatibility,
                    ),
                  )
                else if (compatibility != null)
                  Expanded(
                    child: _CompatibilityView(data: compatibility),
                  )
                else
                  const Expanded(child: _CompatibilitySkeleton()),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class CompatibilityData {
  CompatibilityData({
    required this.score,
    required this.reasons,
    required this.lastUpdated,
    required this.cacheHit,
  });

  factory CompatibilityData.fromJson(Map<String, dynamic> json) {
    final List<String> reasons = <String>[];
    final reasonsJson = json['reasons'];
    if (reasonsJson is List) {
      for (final item in reasonsJson) {
        reasons.add(item.toString());
      }
    }

    return CompatibilityData(
      score: (json['score'] as num?)?.toInt() ?? 0,
      reasons: reasons,
      lastUpdated: json['last_updated']?.toString() ?? '',
      cacheHit: json['cache_hit'] as bool? ?? false,
    );
  }

  final int score;
  final List<String> reasons;
  final String lastUpdated;
  final bool cacheHit;
}

class _CompatibilityView extends StatelessWidget {
  const _CompatibilityView({required this.data});

  final CompatibilityData data;

  @override
  Widget build(BuildContext context) {
    final double progress = (data.score.clamp(0, 100)) / 100.0;

    return ListView(
      children: <Widget>[
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(28),
            gradient: const LinearGradient(
              colors: <Color>[Color(0xFF1F2937), Color(0xFF111827)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            border: Border.all(color: Colors.white12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: const Color(0xFFF5D06B).withValues(alpha: 0.16),
                      border: Border.all(color: const Color(0xFFF5D06B).withValues(alpha: 0.35)),
                    ),
                    child: Center(
                      child: Text(
                        '${data.score}%',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          'Compatibility Score',
                          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                color: Colors.white,
                                fontWeight: FontWeight.w800,
                              ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          data.cacheHit ? 'Loaded instantly from cache' : 'Freshly computed',
                          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                color: Colors.white70,
                              ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  value: progress,
                  minHeight: 12,
                  backgroundColor: Colors.white.withValues(alpha: 0.08),
                  valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFFF5D06B)),
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Last updated: ${data.lastUpdated}',
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                      color: Colors.white54,
                    ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        Text(
          'Why you match',
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w800,
              ),
        ),
        const SizedBox(height: 12),
        ...data.reasons.map(
          (String reason) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: _ReasonTile(text: reason),
          ),
        ),
        if (data.reasons.isEmpty)
          const _ReasonTile(text: 'Not enough signals yet — keep chatting to improve the score.'),
      ],
    );
  }
}

class _ReasonTile extends StatelessWidget {
  const _ReasonTile({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(Icons.check_circle_rounded, size: 18, color: Color(0xFF34D399)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: Colors.white,
                    height: 1.35,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CompatibilitySkeleton extends StatelessWidget {
  const _CompatibilitySkeleton();

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: <Widget>[
        _SkeletonCard(height: 160),
        const SizedBox(height: 16),
        _SkeletonCard(height: 84),
        const SizedBox(height: 12),
        _SkeletonCard(height: 84),
        const SizedBox(height: 12),
        _SkeletonCard(height: 84),
      ],
    );
  }
}

class _SkeletonCard extends StatelessWidget {
  const _SkeletonCard({required this.height});

  final double height;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white12),
      ),
    );
  }
}

class _CompatibilityError extends StatelessWidget {
  const _CompatibilityError({
    required this.message,
    required this.onRetry,
  });

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(Icons.heart_broken_rounded, color: Colors.white54, size: 42),
          const SizedBox(height: 12),
          Text(
            message,
            style: const TextStyle(color: Colors.white),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 14),
          FilledButton(
            onPressed: () => onRetry(),
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFFF5D06B),
              foregroundColor: Colors.black,
            ),
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}
