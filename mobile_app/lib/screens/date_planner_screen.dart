import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../services/chat_client.dart';

class DatePlannerScreen extends ConsumerStatefulWidget {
  const DatePlannerScreen({
    super.key,
    required this.matchId,
  });

  final int matchId;

  @override
  ConsumerState<DatePlannerScreen> createState() => _DatePlannerScreenState();
}

class _DatePlannerScreenState extends ConsumerState<DatePlannerScreen> {
  final Set<String> _sendingSuggestions = <String>{};
  bool _isLoading = true;
  String? _errorMessage;
  DatePlannerData? _plannerData;

  @override
  void initState() {
    super.initState();
    _loadSuggestions();
  }

  Future<void> _loadSuggestions() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final Response<dynamic> response =
          await ref.read(dioProvider).get<dynamic>('/matches/${widget.matchId}/meetup-suggestions');
      final data = response.data;
      if (data is! Map<String, dynamic>) {
        throw StateError('Invalid planner response');
      }

      _plannerData = DatePlannerData.fromJson(data);
      setState(() {
        _isLoading = false;
      });
    } catch (_) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Unable to load date ideas right now.';
      });
    }
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
          content: Text('Sent suggestion for ${venue.name}'),
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
    final venues = _plannerData?.venues ?? const <VenueSuggestionItem>[];

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
                        'Plan a Date',
                        style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                            ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  'Safe, public meetup suggestions near the midpoint between you and your match.',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: Colors.white70,
                        height: 1.35,
                      ),
                ),
                const SizedBox(height: 20),
                if (_isLoading)
                  const Expanded(
                    child: Center(
                      child: CircularProgressIndicator(),
                    ),
                  )
                else if (_errorMessage != null)
                  Expanded(
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: <Widget>[
                          Text(
                            _errorMessage!,
                            style: const TextStyle(color: Colors.white),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 12),
                          OutlinedButton(
                            onPressed: _loadSuggestions,
                            child: const Text('Retry'),
                          ),
                        ],
                      ),
                    ),
                  )
                else
                  Expanded(
                    child: ListView.separated(
                      itemCount: venues.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 14),
                      itemBuilder: (BuildContext context, int index) {
                        final venue = venues[index];
                        final isSending = _sendingSuggestions.contains(venue.name);
                        return _VenueCard(
                          venue: venue,
                          isSending: isSending,
                          onSuggest: () => _suggestVenue(venue),
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

class DatePlannerData {
  DatePlannerData({
    required this.matchId,
    required this.midpoint,
    required this.venues,
  });

  factory DatePlannerData.fromJson(Map<String, dynamic> json) {
    final venuesJson = json['venues'];
    final List<VenueSuggestionItem> venues = <VenueSuggestionItem>[];
    if (venuesJson is List) {
      for (final item in venuesJson) {
        if (item is Map<String, dynamic>) {
          venues.add(VenueSuggestionItem.fromJson(item));
        }
      }
    }

    final midpointJson = json['midpoint'];
    final Map<String, dynamic> midpointMap =
        midpointJson is Map<String, dynamic> ? midpointJson : <String, dynamic>{};

    return DatePlannerData(
      matchId: json['match_id'] is int ? json['match_id'] as int : 0,
      midpoint: GeoPointItem(
        latitude: (midpointMap['latitude'] as num?)?.toDouble() ?? 0,
        longitude: (midpointMap['longitude'] as num?)?.toDouble() ?? 0,
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
        color: const Color(0xFF111827).withValues(alpha: 0.92),
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
            height: 180,
            decoration: BoxDecoration(
              borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
              gradient: LinearGradient(
                colors: <Color>[
                  Colors.white.withValues(alpha: 0.12),
                  Colors.white.withValues(alpha: 0.04),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  const Icon(Icons.local_cafe_rounded, color: Colors.white70, size: 44),
                  const SizedBox(height: 10),
                  Text(
                    venue.venueType.toUpperCase(),
                    style: const TextStyle(
                      color: Colors.white70,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.2,
                    ),
                  ),
                ],
              ),
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
                Text(
                  '${venue.rating.toStringAsFixed(1)}★${venue.distanceMeters != null ? ' • ${venue.distanceMeters}m away' : ''}',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: Colors.white70,
                      ),
                ),
                if (venue.address != null) ...<Widget>[
                  const SizedBox(height: 4),
                  Text(
                    venue.address!,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.white54,
                        ),
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
                    ),
                    child: isSending
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Suggest to Match'),
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
