import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../services/chat_client.dart';

class DateArchitectScreen extends ConsumerStatefulWidget {
  const DateArchitectScreen({
    super.key,
    required this.matchId,
  });

  final int matchId;

  @override
  ConsumerState<DateArchitectScreen> createState() => _DateArchitectScreenState();
}

class _DateArchitectScreenState extends ConsumerState<DateArchitectScreen> {
  final PageController _pageController = PageController(viewportFraction: 0.86);
  final Set<String> _sendingSuggestions = <String>{};
  int _currentPage = 0;

  @override
  void initState() {
    super.initState();
    ref.read(dateArchitectProvider(widget.matchId).notifier).load();
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _suggestVenue(VenueSuggestionItem venue) async {
    if (_sendingSuggestions.contains(venue.name)) {
      return;
    }

    setState(() {
      _sendingSuggestions.add(venue.name);
    });

    try {
      final String proposal = 'Would you like to meet at ${venue.name} (${venue.rating.toStringAsFixed(1)}★)?';
      await ref.read(chatClientProvider).sendMessage(
            matchId: widget.matchId,
            message: proposal,
          );

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Drafted venue suggestion for ${venue.name}'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Unable to suggest venue: $error'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _sendingSuggestions.remove(venue.name);
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final AsyncValue<DateArchitectPlan> planAsync = ref.watch(dateArchitectProvider(widget.matchId));

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
                        'Date Architect',
                        style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -0.4,
                            ),
                      ),
                    ),
                    IconButton(
                      onPressed: () => ref.read(dateArchitectProvider(widget.matchId).notifier).load(),
                      icon: const Icon(Icons.refresh_rounded),
                      tooltip: 'Refresh',
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  'Private venue suggestions with Redis-backed caching and a polished handoff into chat.',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: Colors.white70,
                        height: 1.35,
                      ),
                ),
                const SizedBox(height: 20),
                Expanded(
                  child: planAsync.when(
                    data: (DateArchitectPlan plan) {
                      final List<VenueSuggestionItem> venues = plan.venues;
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          _MidpointCard(plan: plan),
                          const SizedBox(height: 18),
                          Text(
                            'Suggested venues',
                            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                          const SizedBox(height: 12),
                          Expanded(
                            child: PageView.builder(
                              controller: _pageController,
                              itemCount: venues.length,
                              onPageChanged: (int index) {
                                setState(() {
                                  _currentPage = index;
                                });
                              },
                              itemBuilder: (BuildContext context, int index) {
                                final VenueSuggestionItem venue = venues[index];
                                final bool isSending = _sendingSuggestions.contains(venue.name);
                                return AnimatedPadding(
                                  duration: const Duration(milliseconds: 220),
                                  curve: Curves.easeOut,
                                  padding: EdgeInsets.symmetric(
                                    horizontal: index == _currentPage ? 0 : 4,
                                    vertical: index == _currentPage ? 0 : 14,
                                  ),
                                  child: _VenueCard(
                                    venue: venue,
                                    isSending: isSending,
                                    onSuggest: () => _suggestVenue(venue),
                                  ),
                                );
                              },
                            ),
                          ),
                          if (venues.length > 1) ...<Widget>[
                            const SizedBox(height: 10),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: List<Widget>.generate(
                                venues.length,
                                (int index) => AnimatedContainer(
                                  duration: const Duration(milliseconds: 220),
                                  margin: const EdgeInsets.symmetric(horizontal: 4),
                                  width: _currentPage == index ? 18 : 8,
                                  height: 8,
                                  decoration: BoxDecoration(
                                    color: _currentPage == index
                                        ? const Color(0xFFF5D06B)
                                        : Colors.white24,
                                    borderRadius: BorderRadius.circular(999),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ],
                      );
                    },
                    loading: () => const Center(
                      child: _LoadingPanel(),
                    ),
                    error: (Object error, StackTrace stackTrace) => _ConnectionLostPanel(
                      onRetry: () => ref.read(dateArchitectProvider(widget.matchId).notifier).load(),
                    ),
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

final dateArchitectProvider =
    StateNotifierProvider.family<DateArchitectController, AsyncValue<DateArchitectPlan>, int>(
  (ref, int matchId) {
    return DateArchitectController(ref.read(dioProvider), matchId);
  },
);

class DateArchitectController extends StateNotifier<AsyncValue<DateArchitectPlan>> {
  DateArchitectController(this._dio, this._matchId) : super(const AsyncValue.loading());

  final Dio _dio;
  final int _matchId;

  Future<void> load() async {
    state = const AsyncValue.loading();
    try {
      final Response<dynamic> response = await _dio.get<dynamic>('/matches/$_matchId/meetup-suggestions');
      final Map<String, dynamic> data = _asMap(response.data);
      state = AsyncValue.data(DateArchitectPlan.fromJson(data));
    } on DioException catch (error, stackTrace) {
      state = AsyncValue.error(_readErrorMessage(error), stackTrace);
    } catch (error, stackTrace) {
      state = AsyncValue.error('Unable to load date ideas right now.', stackTrace);
    }
  }

  Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map<String, dynamic>) {
      return data;
    }
    if (data is Map) {
      return data.map((dynamic key, dynamic value) => MapEntry<String, dynamic>(key.toString(), value));
    }
    throw StateError('Invalid date architect response');
  }

  String _readErrorMessage(DioException error) {
    final dynamic responseData = error.response?.data;
    if (responseData is Map<String, dynamic>) {
      final dynamic detail = responseData['detail'];
      if (detail is String && detail.isNotEmpty) {
        return detail;
      }
    }
    return 'Unable to load date ideas right now.';
  }
}

class DateArchitectPlan {
  DateArchitectPlan({
    required this.matchId,
    required this.midpoint,
    required this.venues,
  });

  factory DateArchitectPlan.fromJson(Map<String, dynamic> json) {
    final Map<String, dynamic> midpointJson = json['midpoint'] is Map<String, dynamic>
        ? json['midpoint'] as Map<String, dynamic>
        : <String, dynamic>{};

    final venuesJson = json['venues'];
    final List<VenueSuggestionItem> venues = <VenueSuggestionItem>[];
    if (venuesJson is List) {
      for (final dynamic item in venuesJson) {
        if (item is Map<String, dynamic>) {
          venues.add(VenueSuggestionItem.fromJson(item));
        }
      }
    }

    return DateArchitectPlan(
      matchId: json['match_id'] as int? ?? 0,
      midpoint: GeoPointItem(
        latitude: (midpointJson['latitude'] as num?)?.toDouble() ?? 0,
        longitude: (midpointJson['longitude'] as num?)?.toDouble() ?? 0,
      ),
      venues: venues,
    );
  }

  final int matchId;
  final GeoPointItem midpoint;
  final List<VenueSuggestionItem> venues;
}

class GeoPointItem {
  GeoPointItem({
    required this.latitude,
    required this.longitude,
  });

  final double latitude;
  final double longitude;
}

class VenueSuggestionItem {
  VenueSuggestionItem({
    required this.name,
    required this.rating,
    required this.venueType,
    this.address,
    this.photoUrl,
    this.distanceMeters,
  });

  factory VenueSuggestionItem.fromJson(Map<String, dynamic> json) {
    return VenueSuggestionItem(
      name: json['name'] as String? ?? 'Venue',
      rating: (json['rating'] as num?)?.toDouble() ?? 0,
      venueType: json['venue_type'] as String? ?? 'venue',
      address: json['address'] as String?,
      photoUrl: json['photo_url'] as String?,
      distanceMeters: json['distance_meters'] as int?,
    );
  }

  final String name;
  final double rating;
  final String venueType;
  final String? address;
  final String? photoUrl;
  final int? distanceMeters;
}

class _MidpointCard extends StatelessWidget {
  const _MidpointCard({required this.plan});

  final DateArchitectPlan plan;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        color: Colors.white.withValues(alpha: 0.06),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: const Color(0xFFF5D06B).withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Icon(Icons.location_on_rounded, color: Color(0xFFF5D06B)),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Midpoint locked',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
                          ),
                    ),
                    Text(
                      'Coordinates are rounded to 4 decimals for privacy',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Colors.white70,
                          ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            'Lat ${plan.midpoint.latitude.toStringAsFixed(4)}  •  Lng ${plan.midpoint.longitude.toStringAsFixed(4)}',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Match #${plan.matchId}',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Colors.white70,
                ),
          ),
        ],
      ),
    );
  }
}

class _VenueCard extends StatelessWidget {
  const _VenueCard({
    required this.venue,
    required this.isSending,
    required this.onSuggest,
  });

  final VenueSuggestionItem venue;
  final bool isSending;
  final VoidCallback onSuggest;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF111827).withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(28),
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
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(
            height: 210,
            decoration: BoxDecoration(
              borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
              gradient: LinearGradient(
                colors: <Color>[
                  Colors.white.withValues(alpha: 0.14),
                  Colors.white.withValues(alpha: 0.04),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
            child: Stack(
              fit: StackFit.expand,
              children: <Widget>[
                if (venue.photoUrl != null && venue.photoUrl!.isNotEmpty)
                  ClipRRect(
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
                    child: Image.network(
                      venue.photoUrl!,
                      fit: BoxFit.cover,
                      errorBuilder: (BuildContext context, Object error, StackTrace? stackTrace) {
                        return _VenueHeroFallback(venueType: venue.venueType);
                      },
                    ),
                  )
                else
                  _VenueHeroFallback(venueType: venue.venueType),
                Positioned(
                  left: 16,
                  top: 16,
                  child: _TypeChip(text: venue.venueType),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  venue.name,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 6),
                Row(
                  children: <Widget>[
                    const Icon(Icons.star_rounded, color: Color(0xFFF5D06B), size: 18),
                    const SizedBox(width: 6),
                    Text(
                      venue.rating.toStringAsFixed(1),
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: Colors.white70,
                            fontWeight: FontWeight.w700,
                          ),
                    ),
                    if (venue.distanceMeters != null) ...<Widget>[
                      const SizedBox(width: 10),
                      const Icon(Icons.route_rounded, color: Colors.white54, size: 16),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          '${venue.distanceMeters}m away',
                          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                color: Colors.white70,
                              ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ],
                ),
                if (venue.address != null) ...<Widget>[
                  const SizedBox(height: 6),
                  Text(
                    venue.address!,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.white54,
                        ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: isSending ? null : onSuggest,
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFFF5D06B),
                      foregroundColor: Colors.black,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    child: isSending
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Suggest Venue'),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _VenueHeroFallback extends StatelessWidget {
  const _VenueHeroFallback({required this.venueType});

  final String venueType;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(Icons.local_cafe_rounded, color: Colors.white70, size: 48),
          const SizedBox(height: 10),
          Text(
            venueType.toUpperCase(),
            style: const TextStyle(
              color: Colors.white70,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.1,
            ),
          ),
        ],
      ),
    );
  }
}

class _TypeChip extends StatelessWidget {
  const _TypeChip({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.46),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white12),
      ),
      child: Text(
        text.toUpperCase(),
        style: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w700,
          fontSize: 11,
          letterSpacing: 1.1,
        ),
      ),
    );
  }
}

class _LoadingPanel extends StatelessWidget {
  const _LoadingPanel();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white12),
      ),
      child: const Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          SizedBox(
            width: 54,
            height: 54,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              valueColor: AlwaysStoppedAnimation<Color>(Color(0xFFF5D06B)),
            ),
          ),
          SizedBox(height: 16),
          Text(
            'Building your date plan...',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
          ),
          SizedBox(height: 8),
          Text(
            'Fetching premium venue suggestions from the cache.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.white70),
          ),
        ],
      ),
    );
  }
}

class _ConnectionLostPanel extends StatelessWidget {
  const _ConnectionLostPanel({
    required this.onRetry,
  });

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onRetry,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 4),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(28),
          color: const Color(0xFF111827).withValues(alpha: 0.96),
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
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: 60,
              height: 60,
              decoration: BoxDecoration(
                color: const Color(0xFFF5D06B).withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(Icons.wifi_off_rounded, color: Color(0xFFF5D06B), size: 30),
            ),
            const SizedBox(height: 16),
            Text(
              'Connection lost. Tap to retry.',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                  ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'We could not reach your venue suggestions. Tap anywhere on this card to refresh.',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Colors.white70,
                    height: 1.35,
                  ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: onRetry,
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFF5D06B),
                  foregroundColor: Colors.black,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                ),
                child: const Text('Retry now'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
