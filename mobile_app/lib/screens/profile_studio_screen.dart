import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:screen_protector/screen_protector.dart';

import '../controllers/auth_controller.dart';
import '../core/providers.dart';

final profileStudioControllerProvider =
    StateNotifierProvider<ProfileStudioController, ProfileStudioState>((ref) {
  return ProfileStudioController(ref.read(dioProvider));
});

class ProfileStudioScreen extends ConsumerStatefulWidget {
  const ProfileStudioScreen({super.key});

  @override
  ConsumerState<ProfileStudioScreen> createState() => _ProfileStudioScreenState();
}

class _ProfileStudioScreenState extends ConsumerState<ProfileStudioScreen> {
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

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(profileStudioControllerProvider);
    final controller = ref.read(profileStudioControllerProvider.notifier);
    final authState = ref.watch(authControllerProvider);

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: <Color>[Color(0xFF090B16), Color(0xFF111827), Color(0xFF0A0F1F)],
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
                    onPickPhoto: controller.pickPhoto,
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                sliver: SliverToBoxAdapter(
                  child: _ActionChips(
                    selectedCommand: state.selectedCommand,
                    onCommandSelected: controller.selectCommand,
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                sliver: SliverToBoxAdapter(
                  child: _ReputationBadgeSection(
                    reliabilityTier: _readReliabilityTier(authState),
                    reputationScore: _readReputationScore(authState),
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
                sliver: SliverToBoxAdapter(
                  child: _StudioPreview(
                    state: state,
                    onToggleCompare: controller.toggleCompareMode,
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
                sliver: SliverToBoxAdapter(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      _PrimaryActionButton(
                        label: state.isProcessing ? 'Enhancing...' : 'Apply AI Edit',
                        icon: Icons.auto_awesome_rounded,
                        isLoading: state.isProcessing,
                        onPressed: state.canApplyEdit ? controller.applyEdit : null,
                      ),
                      const SizedBox(height: 12),
                      _SaveActionButton(
                        onPressed: state.canSave ? controller.saveToProfile : null,
                      ),
                      if (state.errorMessage != null) ...<Widget>[
                        const SizedBox(height: 16),
                        _ErrorBanner(message: state.errorMessage!),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String? _readReliabilityTier(AuthState authState) {
    return authState.reliabilityTier;
  }

  int? _readReputationScore(AuthState authState) {
    return authState.reputationScore;
  }
}

class ProfileStudioController extends StateNotifier<ProfileStudioState> {
  ProfileStudioController(this._dio) : super(const ProfileStudioState());

  final Dio _dio;
  final ImagePicker _picker = ImagePicker();

  Future<void> pickPhoto() async {
    final XFile? file = await _picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 92,
      maxWidth: 2048,
    );

    if (file == null) {
      return;
    }

    final Uint8List bytes = await file.readAsBytes();
    state = state.copyWith(
      originalImageBytes: bytes,
      originalImageName: file.name,
      editedImageUrl: null,
      compareMode: false,
      errorMessage: null,
    );
  }

  void selectCommand(ProfileEditCommand command) {
    state = state.copyWith(selectedCommand: command, errorMessage: null);
  }

  void toggleCompareMode() {
    state = state.copyWith(compareMode: !state.compareMode);
  }

  Future<void> applyEdit() async {
    if (state.originalImageBytes == null) {
      state = state.copyWith(errorMessage: 'Pick a photo from your gallery first.');
      return;
    }

    state = state.copyWith(isProcessing: true, errorMessage: null);

    try {
      final String encodedImage = base64Encode(state.originalImageBytes!);
      final Response<dynamic> response = await _dio.post<dynamic>(
        '/profile/studio/edit',
        data: <String, dynamic>{
          'image_base64': encodedImage,
          'edit_command': state.selectedCommand.label,
        },
      );

      final data = response.data;
      final String? imageUrl = data is Map<String, dynamic> ? data['image_url'] as String? : null;

      if (imageUrl == null || imageUrl.isEmpty) {
        throw StateError('Missing image_url in response');
      }

      state = state.copyWith(
        isProcessing: false,
        editedImageUrl: imageUrl,
        compareMode: true,
      );
    } on DioException catch (error) {
      state = state.copyWith(
        isProcessing: false,
        errorMessage: _readErrorMessage(error),
      );
    } catch (_) {
      state = state.copyWith(
        isProcessing: false,
        errorMessage: 'Could not process the image right now.',
      );
    }
  }

  Future<void> saveToProfile() async {
    state = state.copyWith(
      errorMessage: 'Profile save integration is ready to connect to your profile API.',
    );
  }

  Future<void> verifyLiveness({
    required int userId,
    required String sessionToken,
  }) async {
    await _dio.post<Map<String, dynamic>>(
      '/security/verify-liveness',
      data: <String, dynamic>{
        'user_id': userId,
        'session_token': sessionToken,
      },
    );
  }

  String _readErrorMessage(DioException error) {
    final responseData = error.response?.data;
    if (responseData is Map<String, dynamic>) {
      final detail = responseData['detail'];
      if (detail is String && detail.isNotEmpty) {
        return detail;
      }
    }
    return 'Unable to edit the photo right now';
  }
}

class ProfileStudioState {
  const ProfileStudioState({
    this.originalImageBytes,
    this.originalImageName,
    this.editedImageUrl,
    this.selectedCommand = ProfileEditCommand.removeBackground,
    this.isProcessing = false,
    this.compareMode = false,
    this.errorMessage,
  });

  final Uint8List? originalImageBytes;
  final String? originalImageName;
  final String? editedImageUrl;
  final ProfileEditCommand selectedCommand;
  final bool isProcessing;
  final bool compareMode;
  final String? errorMessage;

  bool get canApplyEdit => originalImageBytes != null && !isProcessing;
  bool get canSave => editedImageUrl != null && !isProcessing;

  ProfileStudioState copyWith({
    Object? originalImageBytes = _sentinel,
    Object? originalImageName = _sentinel,
    Object? editedImageUrl = _sentinel,
    ProfileEditCommand? selectedCommand,
    bool? isProcessing,
    bool? compareMode,
    Object? errorMessage = _sentinel,
  }) {
    return ProfileStudioState(
      originalImageBytes: identical(originalImageBytes, _sentinel)
          ? this.originalImageBytes
          : originalImageBytes as Uint8List?,
      originalImageName: identical(originalImageName, _sentinel)
          ? this.originalImageName
          : originalImageName as String?,
      editedImageUrl: identical(editedImageUrl, _sentinel)
          ? this.editedImageUrl
          : editedImageUrl as String?,
      selectedCommand: selectedCommand ?? this.selectedCommand,
      isProcessing: isProcessing ?? this.isProcessing,
      compareMode: compareMode ?? this.compareMode,
      errorMessage:
          identical(errorMessage, _sentinel) ? this.errorMessage : errorMessage as String?,
    );
  }

  static const Object _sentinel = Object();
}

enum ProfileEditCommand {
  removeBackground('Remove Background', Icons.layers_clear_rounded),
  autoEnhance('Auto-Enhance', Icons.auto_fix_high_rounded),
  adjustLighting('Adjust Lighting', Icons.wb_sunny_rounded);

  const ProfileEditCommand(this.label, this.icon);

  final String label;
  final IconData icon;
}

class _ReputationBadgeSection extends StatelessWidget {
  const _ReputationBadgeSection({
    required this.reliabilityTier,
    required this.reputationScore,
  });

  final String? reliabilityTier;
  final int? reputationScore;

  @override
  Widget build(BuildContext context) {
    final String tier = (reliabilityTier ?? '').trim().toLowerCase();
    final int score = reputationScore ?? 0;

    if (!_shouldShowBadge(tier, score)) {
      return const SizedBox.shrink();
    }

    final _BadgeSpec spec = _badgeSpecFor(tier, score);

    return AnimatedOpacity(
      duration: const Duration(milliseconds: 240),
      opacity: 1,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          color: Colors.white.withValues(alpha: 0.06),
          border: Border.all(color: spec.borderColor.withValues(alpha: 0.35)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  colors: spec.gradient,
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
              child: Icon(spec.icon, color: Colors.black),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    spec.title,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    spec.subtitle,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.white70,
                          height: 1.3,
                        ),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: <Widget>[
                      _StatPill(
                        label: 'Tier',
                        value: spec.shortLabel,
                      ),
                      _StatPill(
                        label: 'Score',
                        value: score.toString(),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  bool _shouldShowBadge(String tier, int score) {
    if (tier.isEmpty) {
      return false;
    }
    return tier == 'trusted' || tier == 'elite' || score >= 140;
  }

  _BadgeSpec _badgeSpecFor(String tier, int score) {
    if (tier == 'elite' || score >= 180) {
      return const _BadgeSpec(
        title: 'Exceptional Reliability',
        subtitle: 'You’ve reached our highest trust tier. Your profile carries a refined reliability signal.',
        shortLabel: 'Elite',
        icon: Icons.shield_rounded,
        borderColor: Color(0xFFF5D06B),
        gradient: <Color>[Color(0xFFF5D06B), Color(0xFFFFE8A3)],
      );
    }

    return const _BadgeSpec(
      title: 'Highly Reliable',
      subtitle: 'A premium trust signal appears here for members with consistently strong reputation scores.',
      shortLabel: 'Trusted',
      icon: Icons.verified_rounded,
      borderColor: Color(0xFF7C3AED),
      gradient: <Color>[Color(0xFF7C3AED), Color(0xFFB794F4)],
    );
  }
}

class _BadgeSpec {
  const _BadgeSpec({
    required this.title,
    required this.subtitle,
    required this.shortLabel,
    required this.icon,
    required this.borderColor,
    required this.gradient,
  });

  final String title;
  final String subtitle;
  final String shortLabel;
  final IconData icon;
  final Color borderColor;
  final List<Color> gradient;
}

class _StatPill extends StatelessWidget {
  const _StatPill({
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white12),
      ),
      child: RichText(
        text: TextSpan(
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Colors.white70,
                fontWeight: FontWeight.w600,
              ),
          children: <InlineSpan>[
            TextSpan(text: '$label '),
            TextSpan(
              text: value,
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.onPickPhoto});

  final VoidCallback onPickPhoto;

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
                'AI Profile Studio',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.5,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                'Perfect your profile photo with one-tap AI edits before saving it to your profile.',
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                      color: Colors.white70,
                      height: 1.35,
                    ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        _GalleryButton(onTap: onPickPhoto),
      ],
    );
  }
}

class _GalleryButton extends StatelessWidget {
  const _GalleryButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFF1F2937),
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: Colors.white12),
          ),
          child: const Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(Icons.photo_library_rounded, color: Colors.white, size: 20),
              SizedBox(width: 8),
              Text(
                'Gallery',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ActionChips extends StatelessWidget {
  const _ActionChips({
    required this.selectedCommand,
    required this.onCommandSelected,
  });

  final ProfileEditCommand selectedCommand;
  final ValueChanged<ProfileEditCommand> onCommandSelected;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: ProfileEditCommand.values.map((ProfileEditCommand command) {
        final bool isSelected = command == selectedCommand;
        return ChoiceChip(
          label: Text(command.label),
          selected: isSelected,
          onSelected: (_) => onCommandSelected(command),
          avatar: Icon(
            command.icon,
            size: 18,
            color: isSelected ? Colors.black : Colors.white70,
          ),
          labelStyle: TextStyle(
            color: isSelected ? Colors.black : Colors.white,
            fontWeight: FontWeight.w700,
          ),
          selectedColor: const Color(0xFFF5D06B),
          backgroundColor: const Color(0xFF1F2937),
          side: const BorderSide(color: Colors.white12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        );
      }).toList(),
    );
  }
}

class _StudioPreview extends StatelessWidget {
  const _StudioPreview({
    required this.state,
    required this.onToggleCompare,
  });

  final ProfileStudioState state;
  final VoidCallback onToggleCompare;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(30),
        color: const Color(0xFF0F172A).withValues(alpha: 0.92),
        border: Border.all(color: Colors.white12),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            color: Color(0x55000000),
            blurRadius: 24,
            offset: Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          AspectRatio(
            aspectRatio: 0.92,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(24),
              child: Stack(
                fit: StackFit.expand,
                children: <Widget>[
                  if (state.originalImageBytes == null)
                    const _EmptyPreview()
                  else if (state.isProcessing)
                    const _LoadingPreview()
                  else if (state.compareMode && state.editedImageUrl != null)
                    _BeforeAfterView(
                      originalBytes: state.originalImageBytes!,
                      editedImageUrl: state.editedImageUrl!,
                    )
                  else if (state.editedImageUrl != null)
                    _AfterPreview(imageUrl: state.editedImageUrl!)
                  else
                    _OriginalPreview(bytes: state.originalImageBytes!),
                  Positioned(
                    right: 16,
                    top: 16,
                    child: _CompareToggle(
                      enabled: state.originalImageBytes != null && state.editedImageUrl != null,
                      isCompareMode: state.compareMode,
                      onTap: onToggleCompare,
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (state.originalImageName != null) ...<Widget>[
            const SizedBox(height: 12),
            Text(
              state.originalImageName!,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: Colors.white70,
                  ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }
}

class _CompareToggle extends StatelessWidget {
  const _CompareToggle({
    required this.enabled,
    required this.isCompareMode,
    required this.onTap,
  });

  final bool enabled;
  final bool isCompareMode;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: !enabled,
      child: AnimatedOpacity(
        opacity: enabled ? 1 : 0.4,
        duration: const Duration(milliseconds: 180),
        child: Material(
          color: const Color(0xFF111827).withValues(alpha: 0.88),
          borderRadius: BorderRadius.circular(999),
          child: InkWell(
            borderRadius: BorderRadius.circular(999),
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(
                    isCompareMode ? Icons.swap_horiz_rounded : Icons.visibility_rounded,
                    size: 18,
                    color: Colors.white,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    isCompareMode ? 'Compare' : 'View',
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _OriginalPreview extends StatelessWidget {
  const _OriginalPreview({required this.bytes});

  final Uint8List bytes;

  @override
  Widget build(BuildContext context) {
    return Image.memory(bytes, fit: BoxFit.cover);
  }
}

class _AfterPreview extends StatelessWidget {
  const _AfterPreview({required this.imageUrl});

  final String imageUrl;

  @override
  Widget build(BuildContext context) {
    return Image.network(
      imageUrl,
      fit: BoxFit.cover,
      loadingBuilder: (BuildContext context, Widget child, ImageChunkEvent? loadingProgress) {
        if (loadingProgress == null) {
          return child;
        }
        return const _LoadingPreview();
      },
      errorBuilder: (BuildContext context, Object error, StackTrace? stackTrace) {
        return const _LoadingPreview();
      },
    );
  }
}

class _BeforeAfterView extends StatelessWidget {
  const _BeforeAfterView({
    required this.originalBytes,
    required this.editedImageUrl,
  });

  final Uint8List originalBytes;
  final String editedImageUrl;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Expanded(
          child: _SplitPane(
            label: 'Before',
            child: Image.memory(originalBytes, fit: BoxFit.cover),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _SplitPane(
            label: 'After',
            child: Image.network(
              editedImageUrl,
              fit: BoxFit.cover,
              loadingBuilder: (BuildContext context, Widget child, ImageChunkEvent? loadingProgress) {
                if (loadingProgress == null) {
                  return child;
                }
                return const _LoadingPreview();
              },
              errorBuilder: (BuildContext context, Object error, StackTrace? stackTrace) {
                return const _LoadingPreview();
              },
            ),
          ),
        ),
      ],
    );
  }
}

class _SplitPane extends StatelessWidget {
  const _SplitPane({
    required this.label,
    required this.child,
  });

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        ClipRRect(
          borderRadius: BorderRadius.circular(18),
          child: child,
        ),
        Positioned(
          left: 12,
          top: 12,
          child: _PaneLabel(text: label),
        ),
      ],
    );
  }
}

class _PaneLabel extends StatelessWidget {
  const _PaneLabel({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _EmptyPreview extends StatelessWidget {
  const _EmptyPreview();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: <Color>[Color(0xFF1F2937), Color(0xFF111827)],
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
        ),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: 92,
              height: 92,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: 0.06),
                border: Border.all(color: Colors.white12),
              ),
              child: const Icon(
                Icons.add_a_photo_rounded,
                color: Colors.white70,
                size: 40,
              ),
            ),
            const SizedBox(height: 18),
            const Text(
              'Pick a portrait to start editing',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Your AI-edited result will appear here.',
              style: TextStyle(color: Colors.white70),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadingPreview extends StatelessWidget {
  const _LoadingPreview();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: <Color>[Color(0xFF111827), Color(0xFF1F2937), Color(0xFF111827)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: const Center(
        child: SizedBox(
          width: 56,
          height: 56,
          child: CircularProgressIndicator(
            strokeWidth: 3,
            valueColor: AlwaysStoppedAnimation<Color>(Color(0xFFF5D06B)),
          ),
        ),
      ),
    );
  }
}

class _PrimaryActionButton extends StatelessWidget {
  const _PrimaryActionButton({
    required this.label,
    required this.icon,
    required this.onPressed,
    required this.isLoading,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onPressed;
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      onPressed: onPressed,
      icon: isLoading
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(
                strokeWidth: 2.2,
                valueColor: AlwaysStoppedAnimation<Color>(Colors.black),
              ),
            )
          : Icon(icon),
      label: Text(label),
      style: FilledButton.styleFrom(
        backgroundColor: const Color(0xFFF5D06B),
        foregroundColor: Colors.black,
        padding: const EdgeInsets.symmetric(vertical: 16),
        textStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      ),
    );
  }
}

class _SaveActionButton extends StatelessWidget {
  const _SaveActionButton({required this.onPressed});

  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: onPressed,
      icon: const Icon(Icons.verified_rounded),
      label: const Text('Save to Profile'),
      style: OutlinedButton.styleFrom(
        foregroundColor: Colors.white,
        side: const BorderSide(color: Colors.white24),
        padding: const EdgeInsets.symmetric(vertical: 16),
        textStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
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
            child: Text(
              message,
              style: const TextStyle(color: Colors.white),
            ),
          ),
        ],
      ),
    );
  }
}
