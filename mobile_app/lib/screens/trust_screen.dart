import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../controllers/auth_controller.dart';
import '../main.dart';

final trustControllerProvider = StateNotifierProvider<TrustController, TrustState>((ref) {
  return TrustController(ref.read(dioProvider));
});

class TrustScreen extends ConsumerWidget {
  const TrustScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(trustControllerProvider);
    final controller = ref.read(trustControllerProvider.notifier);
    final authState = ref.watch(authControllerProvider);

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: <Color>[Color(0xFF07111F), Color(0xFF0B1220), Color(0xFF050816)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: SafeArea(
          child: CustomScrollView(
            slivers: <Widget>[
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 12),
                sliver: SliverToBoxAdapter(
                  child: _Header(
                    score: state.score,
                    tier: state.tier,
                    verified: state.verified,
                    cached: state.cached,
                    onRefresh: controller.loadTrustScore,
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                sliver: SliverToBoxAdapter(
                  child: _TrustCard(state: state),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
                sliver: SliverToBoxAdapter(
                  child: _VerificationCard(
                    state: state,
                    userId: authState.userId,
                    onPickImage: controller.pickSelfie,
                    onVerify: controller.submitSelfieVerification,
                  ),
                ),
              ),
              if (state.errorMessage != null)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
                  sliver: SliverToBoxAdapter(
                    child: _ErrorBanner(message: state.errorMessage!),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class TrustController extends StateNotifier<TrustState> {
  TrustController(this._dio) : super(const TrustState());

  final Dio _dio;
  final ImagePicker _picker = ImagePicker();

  Future<void> loadTrustScore() async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      final Response<dynamic> response = await _dio.get<dynamic>('/trust/summary/1');
      final data = response.data;
      if (data is! Map<String, dynamic>) {
        throw StateError('Invalid trust response');
      }
      state = state.copyWith(
        isLoading: false,
        score: (data['score'] as num?)?.toInt() ?? 0,
        tier: (data['tier'] as String?) ?? 'Low',
        verified: data['verified'] as bool? ?? false,
        cached: data['cached'] as bool? ?? false,
      );
    } on DioException catch (error) {
      state = state.copyWith(isLoading: false, errorMessage: _readErrorMessage(error));
    } catch (_) {
      state = state.copyWith(isLoading: false, errorMessage: 'Unable to load trust score.');
    }
  }

  Future<void> pickSelfie() async {
    final XFile? file = await _picker.pickImage(source: ImageSource.gallery, imageQuality: 90);
    if (file == null) {
      return;
    }
    final Uint8List bytes = await file.readAsBytes();
    state = state.copyWith(selfieBytes: bytes, selfieName: file.name, errorMessage: null);
  }

  Future<void> submitSelfieVerification({required int userId}) async {
    if (state.selfieBytes == null) {
      state = state.copyWith(errorMessage: 'Pick a clear selfie first.');
      return;
    }

    state = state.copyWith(isVerifying: true, errorMessage: null);
    try {
      final String encoded = base64Encode(state.selfieBytes!);
      final Response<dynamic> response = await _dio.post<dynamic>(
        '/trust/verify/selfie',
        data: <String, dynamic>{
          'user_id': userId,
          'image_base64': encoded,
        },
      );
      final data = response.data;
      if (data is Map<String, dynamic>) {
        state = state.copyWith(
          score: (data['score'] as num?)?.toInt() ?? state.score,
          tier: (data['tier'] as String?) ?? state.tier,
          verified: data['verified'] as bool? ?? state.verified,
          cached: data['cached'] as bool? ?? false,
        );
      }
      state = state.copyWith(isVerifying: false, successMessage: 'Verification updated.');
    } on DioException catch (error) {
      state = state.copyWith(isVerifying: false, errorMessage: _readErrorMessage(error));
    } catch (_) {
      state = state.copyWith(isVerifying: false, errorMessage: 'Verification failed.');
    }
  }

  String _readErrorMessage(DioException error) {
    final responseData = error.response?.data;
    if (responseData is Map<String, dynamic>) {
      final detail = responseData['detail'];
      if (detail is String && detail.isNotEmpty) {
        return detail;
      }
    }
    return 'Request failed.';
  }
}

class TrustState {
  const TrustState({
    this.score = 0,
    this.tier = 'Low',
    this.verified = false,
    this.cached = false,
    this.selfieBytes,
    this.selfieName,
    this.isLoading = false,
    this.isVerifying = false,
    this.errorMessage,
    this.successMessage,
  });

  final int score;
  final String tier;
  final bool verified;
  final bool cached;
  final Uint8List? selfieBytes;
  final String? selfieName;
  final bool isLoading;
  final bool isVerifying;
  final String? errorMessage;
  final String? successMessage;

  TrustState copyWith({
    int? score,
    String? tier,
    bool? verified,
    bool? cached,
    Object? selfieBytes = _sentinel,
    Object? selfieName = _sentinel,
    bool? isLoading,
    bool? isVerifying,
    Object? errorMessage = _sentinel,
    Object? successMessage = _sentinel,
  }) {
    return TrustState(
      score: score ?? this.score,
      tier: tier ?? this.tier,
      verified: verified ?? this.verified,
      cached: cached ?? this.cached,
      selfieBytes: identical(selfieBytes, _sentinel) ? this.selfieBytes : selfieBytes as Uint8List?,
      selfieName: identical(selfieName, _sentinel) ? this.selfieName : selfieName as String?,
      isLoading: isLoading ?? this.isLoading,
      isVerifying: isVerifying ?? this.isVerifying,
      errorMessage: identical(errorMessage, _sentinel) ? this.errorMessage : errorMessage as String?,
      successMessage:
          identical(successMessage, _sentinel) ? this.successMessage : successMessage as String?,
    );
  }

  static const Object _sentinel = Object();
}

class _Header extends StatelessWidget {
  const _Header({
    required this.score,
    required this.tier,
    required this.verified,
    required this.cached,
    required this.onRefresh,
  });

  final int score;
  final String tier;
  final bool verified;
  final bool cached;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                'Trust Score',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                'A fast, cached trust layer that keeps verification visible and abuse friction low.',
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Colors.white70),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        _RefreshButton(onTap: onRefresh),
      ],
    );
  }
}

class _RefreshButton extends StatelessWidget {
  const _RefreshButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFF1F2937),
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: const Padding(
          padding: EdgeInsets.all(14),
          child: Icon(Icons.refresh_rounded, color: Colors.white),
        ),
      ),
    );
  }
}

class _TrustCard extends StatelessWidget {
  const _TrustCard({required this.state});

  final TrustState state;

  @override
  Widget build(BuildContext context) {
    final Color accent = state.score >= 70
        ? const Color(0xFF34D399)
        : state.score >= 40
            ? const Color(0xFFFBBF24)
            : const Color(0xFFF87171);

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        color: Colors.white.withValues(alpha: 0.05),
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
                  color: accent.withValues(alpha: 0.18),
                ),
                child: Center(
                  child: Text(
                    '${state.score}',
                    style: TextStyle(
                      color: accent,
                      fontWeight: FontWeight.w900,
                      fontSize: 22,
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
                      state.tier,
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      state.verified ? 'Verified User' : 'Verification pending',
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
                    ),
                  ],
                ),
              ),
              if (state.cached) const _Badge(text: 'Cached'),
            ],
          ),
          const SizedBox(height: 18),
          LinearProgressIndicator(
            value: state.score / 100.0,
            minHeight: 10,
            backgroundColor: Colors.white12,
            valueColor: AlwaysStoppedAnimation<Color>(accent),
            borderRadius: BorderRadius.circular(99),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: <Widget>[
              _Badge(text: '${state.score}%'),
              _Badge(text: state.verified ? 'Verified' : 'Not verified'),
              _Badge(text: state.tier),
            ],
          ),
        ],
      ),
    );
  }
}

class _VerificationCard extends StatelessWidget {
  const _VerificationCard({
    required this.state,
    required this.userId,
    required this.onPickImage,
    required this.onVerify,
  });

  final TrustState state;
  final int? userId;
  final VoidCallback onPickImage;
  final Future<void> Function({required int userId}) onVerify;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        color: Colors.white.withValues(alpha: 0.05),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            'Selfie verification',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Upload a selfie for liveness verification. Images stay protected and verification is rate-limited.',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
          ),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: onPickImage,
            icon: const Icon(Icons.photo_library_rounded),
            label: const Text('Choose selfie'),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: state.isVerifying || userId == null ? null : () => onVerify(userId: userId!),
            icon: state.isVerifying
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black),
                  )
                : const Icon(Icons.verified_rounded),
            label: Text(state.isVerifying ? 'Verifying...' : 'Submit verification'),
          ),
          if (userId == null) ...<Widget>[
            const SizedBox(height: 10),
            const Text(
              'Sign in to verify your identity.',
              style: TextStyle(color: Colors.white70),
            ),
          ],
          if (state.selfieName != null) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              'Selected: ${state.selfieName}',
              style: const TextStyle(color: Colors.white70),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          if (state.successMessage != null) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              state.successMessage!,
              style: const TextStyle(color: Color(0xFF86EFAC)),
            ),
          ],
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white12),
      ),
      child: Text(
        text,
        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF7F1D1D).withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFFCA5A5).withValues(alpha: 0.3)),
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.error_outline_rounded, color: Color(0xFFFCA5A5)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(message, style: const TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }
}
