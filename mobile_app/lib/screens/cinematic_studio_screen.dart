import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:screen_protector/screen_protector.dart';

import '../core/providers.dart';

class CinematicStudioScreen extends ConsumerStatefulWidget {
  const CinematicStudioScreen({super.key});

  @override
  ConsumerState<CinematicStudioScreen> createState() => _CinematicStudioScreenState();
}

class _CinematicStudioScreenState extends ConsumerState<CinematicStudioScreen> {
  final ImagePicker _picker = ImagePicker();
  final TextEditingController _editModeController = TextEditingController(text: 'relight');
  StreamSubscription<Map<String, dynamic>>? _websocketSubscription;
  Timer? _websocketTimeout;

  Uint8List? _originalBytes;
  String? _fileName;
  String? _editedImageUrl;
  String? _currentJobId;
  bool _isUploading = false;
  bool _isWaitingForWebhook = false;
  bool _showCompare = false;
  String? _errorMessage;
  double _sliderPosition = 0.5;

  @override
  void initState() {
    super.initState();
    ScreenProtector.protectDataLeakageOn();
    ScreenProtector.preventScreenshotOn();
  }

  @override
  void dispose() {
    _websocketTimeout?.cancel();
    _websocketSubscription?.cancel();
    _editModeController.dispose();
    ScreenProtector.preventScreenshotOff();
    ScreenProtector.protectDataLeakageOff();
    super.dispose();
  }

  Future<void> _pickPhoto() async {
    final XFile? file = await _picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 80,
      maxWidth: 1920,
      maxHeight: 1920,
    );

    if (file == null) {
      return;
    }

    final Uint8List bytes = await file.readAsBytes();
    if (!mounted) {
      return;
    }

    setState(() {
      _originalBytes = bytes;
      _fileName = file.name;
      _editedImageUrl = null;
      _currentJobId = null;
      _showCompare = false;
      _isWaitingForWebhook = false;
      _errorMessage = null;
      _sliderPosition = 0.5;
    });
  }

  Future<void> _startEdit() async {
    final Uint8List? bytes = _originalBytes;
    if (bytes == null) {
      setState(() {
        _errorMessage = 'Choose a photo before starting the cinematic edit.';
      });
      return;
    }

    setState(() {
      _isUploading = true;
      _isWaitingForWebhook = false;
      _errorMessage = null;
      _editedImageUrl = null;
      _currentJobId = null;
      _showCompare = false;
    });

    try {
      // Backend returns a presigned S3 PUT URL and object key. The app uploads the
      // raw file bytes directly to S3, keeping the media stream off the API server.
      final Response<dynamic> prepareResponse = await ref.read(dioProvider).post<dynamic>(
        '/profile/cinematic/prepare',
        data: FormData.fromMap(
          <String, dynamic>{
            'edit_mode': _editModeController.text.trim(),
            'image_file': MultipartFile.fromBytes(
              bytes,
              filename: _fileName ?? 'cinematic.jpg',
            ),
          },
        ),
      );

      final Map<String, dynamic> payload = _decodeObject(prepareResponse.data);
      final String presignedUrl = payload['original_presigned_url']?.toString() ?? '';
      final String objectKey = payload['original_object_key']?.toString() ?? '';
      final String? providerJobId = payload['provider_job_id']?.toString();

      if (presignedUrl.isEmpty || objectKey.isEmpty) {
        throw StateError('Missing cinematic upload metadata');
      }

      // Direct-to-S3 upload: the presigned URL authorizes a PUT request from the
      // client without exposing AWS credentials or proxying the image through FastAPI.
      await ref.read(dioProvider).put<dynamic>(
            presignedUrl,
            data: bytes,
            options: Options(
              headers: <String, dynamic>{
                'Content-Type': 'image/jpeg',
                'Content-Length': bytes.length.toString(),
              },
              responseType: ResponseType.plain,
              followRedirects: false,
            ),
          );

      if (!mounted) {
        return;
      }

      setState(() {
        _isUploading = false;
        _isWaitingForWebhook = true;
        _currentJobId = providerJobId ?? objectKey;
      });

      await _listenForWebhook(jobId: _currentJobId!);
    } on DioException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isUploading = false;
        _isWaitingForWebhook = false;
        _errorMessage = _readErrorMessage(error);
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isUploading = false;
        _isWaitingForWebhook = false;
        _errorMessage = error.toString();
      });
    }
  }

  Future<void> _listenForWebhook({required String jobId}) async {
    final chatClient = ref.read(chatClientProvider);

    // WebSocket listener integration: the backend publishes ai-image-complete
    // notifications on the existing realtime stream, so we wait for that event
    // instead of polling while the AI pipeline finishes.
    await chatClient.connect(0);
    await _websocketSubscription?.cancel();
    _websocketTimeout?.cancel();

    _websocketTimeout = Timer(const Duration(seconds: 60), () {
      if (!mounted || !_isWaitingForWebhook) {
        return;
      }
      setState(() {
        _isWaitingForWebhook = false;
        _isUploading = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('High traffic. Your image will appear in your profile shortly.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    });

    _websocketSubscription = chatClient.messages.listen((Map<String, dynamic> event) {
      final String eventName = event['event']?.toString() ?? event['type']?.toString() ?? '';
      final String receivedJobId = event['provider_job_id']?.toString() ?? '';
      if (eventName != 'ai_image_complete') {
        return;
      }
      if (receivedJobId.isNotEmpty && receivedJobId != jobId) {
        return;
      }

      final String imageUrl = event['image_url']?.toString() ?? event['output_image_url']?.toString() ?? '';
      if (imageUrl.isEmpty || !mounted) {
        return;
      }

      _websocketTimeout?.cancel();
      setState(() {
        _editedImageUrl = imageUrl;
        _isWaitingForWebhook = false;
        _isUploading = false;
        _showCompare = true;
        _sliderPosition = 0.5;
      });
    });
  }

  Map<String, dynamic> _decodeObject(dynamic data) {
    if (data is Map<String, dynamic>) {
      return data;
    }
    if (data is Map) {
      return data.map((dynamic key, dynamic value) => MapEntry<String, dynamic>(key.toString(), value));
    }
    throw StateError('Unexpected response payload');
  }

  String _readErrorMessage(DioException error) {
    final dynamic responseData = error.response?.data;
    if (responseData is Map<String, dynamic>) {
      final dynamic detail = responseData['detail'];
      if (detail is String && detail.isNotEmpty) {
        return detail;
      }
    }
    return 'Unable to process the photo right now.';
  }

  @override
  Widget build(BuildContext context) {
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
                        'Cinematic Profile Studio',
                        style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -0.4,
                            ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  'Direct-to-S3 uploads, secure processing, and an elegant before/after reveal when the webhook lands.',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: Colors.white70,
                        height: 1.35,
                      ),
                ),
                const SizedBox(height: 20),
                Expanded(
                  child: ListView(
                    children: <Widget>[
                      _PreviewCard(
                        originalBytes: _originalBytes,
                        editedImageUrl: _editedImageUrl,
                        isWaitingForWebhook: _isWaitingForWebhook,
                        showCompare: _showCompare,
                        sliderPosition: _sliderPosition,
                        onSliderChanged: (double value) {
                          setState(() {
                            _sliderPosition = value;
                          });
                        },
                      ),
                      const SizedBox(height: 16),
                      _EditModeField(controller: _editModeController),
                      const SizedBox(height: 16),
                      Row(
                        children: <Widget>[
                          Expanded(
                            child: FilledButton.icon(
                              onPressed: _pickPhoto,
                              icon: const Icon(Icons.photo_library_rounded),
                              label: const Text('Choose Photo'),
                              style: FilledButton.styleFrom(
                                backgroundColor: const Color(0xFF2563EB),
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(vertical: 16),
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      FilledButton.icon(
                        onPressed: _isUploading || _isWaitingForWebhook ? null : _startEdit,
                        icon: _isUploading
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2.2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.black),
                                ),
                              )
                            : const Icon(Icons.auto_awesome_rounded),
                        label: Text(
                          _isUploading
                              ? 'Preparing secure upload...'
                              : _isWaitingForWebhook
                                  ? 'Waiting for AI webhook...'
                                  : 'Generate Cinematic Edit',
                        ),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFFF5D06B),
                          foregroundColor: Colors.black,
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          textStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
                        ),
                      ),
                      if (_errorMessage != null) ...<Widget>[
                        const SizedBox(height: 16),
                        _ErrorBanner(message: _errorMessage!),
                      ],
                    ],
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

class _EditModeField extends StatelessWidget {
  const _EditModeField({required this.controller});

  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      style: const TextStyle(color: Colors.white),
      decoration: InputDecoration(
        labelText: 'Edit mode',
        labelStyle: const TextStyle(color: Colors.white70),
        hintText: 'relight, upscale, remove-background',
        hintStyle: const TextStyle(color: Colors.white38),
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.06),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
    );
  }
}

class _PreviewCard extends StatelessWidget {
  const _PreviewCard({
    required this.originalBytes,
    required this.editedImageUrl,
    required this.isWaitingForWebhook,
    required this.showCompare,
    required this.sliderPosition,
    required this.onSliderChanged,
  });

  final Uint8List? originalBytes;
  final String? editedImageUrl;
  final bool isWaitingForWebhook;
  final bool showCompare;
  final double sliderPosition;
  final ValueChanged<double> onSliderChanged;

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
      child: AspectRatio(
        aspectRatio: 0.92,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              if (originalBytes == null)
                const _EmptyState()
              else if (isWaitingForWebhook)
                const _WebhookWaitingState()
              else if (showCompare && editedImageUrl != null)
                _BeforeAfterSlider(
                  originalBytes: originalBytes!,
                  editedImageUrl: editedImageUrl!,
                  sliderPosition: sliderPosition,
                  onSliderChanged: onSliderChanged,
                )
              else if (editedImageUrl != null)
                Image.network(
                  editedImageUrl!,
                  fit: BoxFit.cover,
                  loadingBuilder: (BuildContext context, Widget child, ImageChunkEvent? progress) {
                    if (progress == null) {
                      return child;
                    }
                    return const _WebhookWaitingState();
                  },
                )
              else
                Image.memory(originalBytes!, fit: BoxFit.cover),
              Positioned(
                left: 16,
                top: 16,
                child: _Badge(text: showCompare ? 'Before / After' : 'Original'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BeforeAfterSlider extends StatelessWidget {
  const _BeforeAfterSlider({
    required this.originalBytes,
    required this.editedImageUrl,
    required this.sliderPosition,
    required this.onSliderChanged,
  });

  final Uint8List originalBytes;
  final String editedImageUrl;
  final double sliderPosition;
  final ValueChanged<double> onSliderChanged;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        return GestureDetector(
          onHorizontalDragUpdate: (DragUpdateDetails details) {
            final double next = (details.localPosition.dx / constraints.maxWidth).clamp(0.0, 1.0);
            onSliderChanged(next);
          },
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              Image.network(editedImageUrl, fit: BoxFit.cover),
              ClipRect(
                child: Align(
                  alignment: Alignment.centerLeft,
                  widthFactor: sliderPosition,
                  child: Image.memory(originalBytes, fit: BoxFit.cover),
                ),
              ),
              Positioned(
                left: (constraints.maxWidth * sliderPosition) - 18,
                top: 0,
                bottom: 0,
                child: Container(
                  width: 36,
                  alignment: Alignment.center,
                  child: Container(
                    width: 3,
                    color: Colors.white,
                  ),
                ),
              ),
              Positioned(
                left: (constraints.maxWidth * sliderPosition) - 22,
                top: (constraints.maxHeight / 2) - 22,
                child: Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.55),
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white70),
                  ),
                  child: const Icon(Icons.drag_indicator_rounded, color: Colors.white),
                ),
              ),
            ],
          ),
        );
      },
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
        color: Colors.black.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

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
      child: const Center(
        child: Text(
          'Choose a portrait to begin',
          style: TextStyle(color: Colors.white70, fontWeight: FontWeight.w700),
        ),
      ),
    );
  }
}

class _WebhookWaitingState extends StatelessWidget {
  const _WebhookWaitingState();

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
