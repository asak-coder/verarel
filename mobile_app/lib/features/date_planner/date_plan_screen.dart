import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../core/providers.dart';
import '../../core/services/date_plan_service.dart';

final datePlanProvider = FutureProvider.family<DatePlanResult, int>(
  (ref, int matchId) async {
    return ref.read(datePlanServiceProvider).loadDatePlan(matchId);
  },
);

class DatePlanScreen extends ConsumerWidget {
  const DatePlanScreen({
    super.key,
    required this.matchId,
  });

  final int matchId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<DatePlanResult> planAsync = ref.watch(datePlanProvider(matchId));

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
            child: planAsync.when(
              data: (DatePlanResult plan) => _DatePlanContent(plan: plan),
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (Object error, StackTrace stackTrace) => _ErrorView(
                onRetry: () => ref.invalidate(datePlanProvider(matchId)),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _DatePlanContent extends StatelessWidget {
  const _DatePlanContent({required this.plan});

  final DatePlanResult plan;

  @override
  Widget build(BuildContext context) {
    final LatLng center = plan.center;
    final List<Map<String, dynamic>> venues = plan.venues;

    return Column(
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
                'Date Planner',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Container(
          height: 220,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: Colors.white12),
          ),
          clipBehavior: Clip.antiAlias,
          child: FlutterMap(
            options: MapOptions(
              initialCenter: center,
              initialZoom: 13,
            ),
            children: <Widget>[
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.verarel.mobile',
              ),
              MarkerLayer(
                markers: <Marker>[
                  Marker(
                    point: center,
                    width: 48,
                    height: 48,
                    child: const Icon(Icons.location_pin, color: Color(0xFFF5D06B), size: 42),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        Text(
          'Suggested venues',
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w800,
              ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          height: 180,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: venues.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (BuildContext context, int index) {
              final Map<String, dynamic> venue = venues[index];
              return _VenueCard(venue: venue);
            },
          ),
        ),
      ],
    );
  }
}

class _VenueCard extends StatelessWidget {
  const _VenueCard({required this.venue});

  final Map<String, dynamic> venue;

  @override
  Widget build(BuildContext context) {
    final String name = venue['name']?.toString() ?? 'Venue';
    final String address = venue['address']?.toString() ?? 'Suggested public meetup';
    final String rating = venue['rating']?.toString() ?? '0.0';

    return Container(
      width: 260,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(
            height: 84,
            width: double.infinity,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(18),
              gradient: const LinearGradient(
                colors: <Color>[Color(0xFF7C3AED), Color(0xFF2563EB)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
            child: const Center(
              child: Icon(Icons.local_cafe_rounded, color: Colors.white, size: 34),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            name,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 4),
          Text(
            address,
            style: const TextStyle(color: Colors.white70, height: 1.25),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const Spacer(),
          Row(
            children: <Widget>[
              const Icon(Icons.star_rounded, color: Color(0xFFF5D06B), size: 18),
              const SizedBox(width: 4),
              Text(
                rating,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(Icons.map_outlined, color: Colors.white54, size: 44),
          const SizedBox(height: 12),
          const Text(
            'Unable to load date plan right now.',
            style: TextStyle(color: Colors.white),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: onRetry,
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}
