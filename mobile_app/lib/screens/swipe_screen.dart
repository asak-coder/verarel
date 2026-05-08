import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:screen_protector/screen_protector.dart';

import '../controllers/auth_controller.dart';
import '../main.dart';
import '../services/chat_client.dart';

class SwipeScreen extends ConsumerStatefulWidget {
  const SwipeScreen({super.key});

  @override
  ConsumerState<SwipeScreen> createState() => _SwipeScreenState();
}

class _SwipeScreenState extends ConsumerState<SwipeScreen> {
  Offset _dragOffset = Offset.zero;
  double _dragAngle = 0;

  @override
  void initState() {
    super.initState();
    ScreenProtector.protectDataLeakageOn();
    ScreenProtector.preventScreenshotOn();
  }

  @override
  void dispose() {
    ScreenProtector.preventScreenshotOff();
    ScreenProtector.protectDataLeakageOff();
    super.dispose();
  }

  Future<void> _runMockLivenessCheck() async {
    final authState = ref.read(authControllerProvider);
    final int userId = authState.userId ?? 1;

    // Mock biometric SDK output: the real app would receive this from FaceTec/Onfido.
    const String sessionToken = 'mock-liveness-session-token';
    await ref.read(authControllerProvider.notifier).submitLivenessSession(
          userId: userId,
          sessionToken: sessionToken,
        );
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);
    final chatClient = ref.read(chatClientProvider);

    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: <Widget>[
            Positioned.fill(
              child: Container(
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    colors: <Color>[Color(0xFF111827), Color(0xFF0B1020)],
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Discover',
                    style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    authState.accessToken == null
                        ? 'Sign in to start matching'
                        : 'Your next premium match is ready',
                    style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                          color: Colors.white70,
                        ),
                  ),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: <Widget>[
                      FilledButton.icon(
                        onPressed: () => context.go('/profile-studio'),
                        icon: const Icon(Icons.photo_camera_back_rounded),
                        label: const Text('Open AI Profile Studio'),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFFF5D06B),
                          foregroundColor: Colors.black,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                        ),
                      ),
                      FilledButton.icon(
                        onPressed: () => context.go('/date-planner/1'),
                        icon: const Icon(Icons.place_rounded),
                        label: const Text('Plan a Date'),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF2563EB),
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                        ),
                      ),
                      FilledButton.icon(
                        onPressed: () => context.go('/compatibility/1'),
                        icon: const Icon(Icons.favorite_rounded),
                        label: const Text('View Compatibility'),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF7C3AED),
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                        ),
                      ),
                      OutlinedButton.icon(
                        onPressed: authState.accessToken == null ? null : _runMockLivenessCheck,
                        icon: const Icon(Icons.verified_user_rounded),
                        label: const Text('Run Liveness Check'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.white,
                          side: const BorderSide(color: Colors.white24),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const Spacer(),
                  Center(
                    child: GestureDetector(
                      onPanUpdate: (DragUpdateDetails details) {
                        // Track horizontal drag to drive the swipe card movement.
                        setState(() {
                          _dragOffset += details.delta;
                          _dragAngle = (_dragOffset.dx / 300).clamp(-0.35, 0.35);
                        });
                      },
                      onPanEnd: (DragEndDetails details) {
                        // Commit the swipe state based on velocity, then snap back.
                        final bool accepted = _dragOffset.dx.abs() > 120 ||
                            details.velocity.pixelsPerSecond.dx.abs() > 900;
                        if (accepted && _dragOffset.dx > 0) {
                          chatClient.preloadMatchPreview(matchId: 1);
                        }
                        setState(() {
                          _dragOffset = Offset.zero;
                          _dragAngle = 0;
                        });
                      },
                      child: Transform.translate(
                        offset: _dragOffset,
                        child: Transform.rotate(
                          angle: _dragAngle,
                          child: _SwipeCard(
                            isAuthenticated: authState.accessToken != null,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const Spacer(),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: <Widget>[
                      _ActionButton(
                        icon: Icons.close_rounded,
                        color: const Color(0xFFFF6B6B),
                        onTap: () {},
                      ),
                      _ActionButton(
                        icon: Icons.star_rounded,
                        color: const Color(0xFF8B5CF6),
                        onTap: () {},
                      ),
                      _ActionButton(
                        icon: Icons.favorite_rounded,
                        color: const Color(0xFF34D399),
                        onTap: () {},
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SwipeCard extends StatelessWidget {
  const _SwipeCard({required this.isAuthenticated});

  final bool isAuthenticated;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 340,
      height: 520,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(32),
        color: const Color(0xFF111827),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            blurRadius: 30,
            spreadRadius: 2,
            color: Color(0x55000000),
          ),
        ],
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(24),
              child: Container(
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    colors: <Color>[Color(0xFF7C3AED), Color(0xFF2563EB)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                ),
                child: Stack(
                  children: <Widget>[
                    Positioned(
                      left: 16,
                      top: 16,
                      child: _ScoreBadge(
                        label: '92%',
                        subtitle: 'Compatibility',
                      ),
                    ),
                    Positioned(
                      left: 16,
                      right: 16,
                      bottom: 16,
                      child: Text(
                        'Match reason: shared values, nearby distance, and aligned lifestyle preferences.',
                        style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w600,
                            ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Ari, 27',
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 4),
          Text(
            isAuthenticated
                ? 'Ready for swipe, chat, and verification flow'
                : 'Authenticate to unlock messaging and verification',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Colors.white70,
                ),
          ),
        ],
      ),
    );
  }
}

class _ScoreBadge extends StatelessWidget {
  const _ScoreBadge({required this.label, required this.subtitle});

  final String label;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.32),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            label,
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                ),
          ),
          Text(
            subtitle,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: Colors.white70,
                ),
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkResponse(
      onTap: onTap,
      radius: 36,
      child: Container(
        width: 64,
        height: 64,
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          shape: BoxShape.circle,
          border: Border.all(color: color.withValues(alpha: 0.35)),
        ),
        child: Icon(icon, color: color, size: 30),
      ),
    );
  }
}
