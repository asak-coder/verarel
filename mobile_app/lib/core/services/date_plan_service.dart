import 'package:dio/dio.dart';
import 'package:latlong2/latlong.dart';

class DatePlanService {
  DatePlanService(this._dio);

  final Dio _dio;

  Future<DatePlanResult> loadDatePlan(int matchId) async {
    final Response<dynamic> response = await _dio.get<dynamic>('/api/date-plan/$matchId');

    final dynamic data = response.data;
    if (data is! Map<String, dynamic>) {
      throw StateError('Invalid date plan response');
    }

    final dynamic midpointJson = data['midpoint'];
    final Map<String, dynamic> midpointMap =
        midpointJson is Map<String, dynamic> ? midpointJson : <String, dynamic>{};

    final List<DatePlanVenue> venues = <DatePlanVenue>[];
    final dynamic venuesJson = data['venues'];
    if (venuesJson is List) {
      for (final dynamic item in venuesJson) {
        if (item is Map<String, dynamic>) {
          venues.add(DatePlanVenue.fromJson(item));
        }
      }
    }

    return DatePlanResult(
      matchId: _readInt(data['match_id']),
      center: LatLng(
        _readDouble(midpointMap['latitude']),
        _readDouble(midpointMap['longitude']),
      ),
      venues: venues,
    );
  }

  int _readInt(dynamic value) => value is num ? value.toInt() : int.tryParse(value?.toString() ?? '') ?? 0;

  double _readDouble(dynamic value) => value is num ? value.toDouble() : double.tryParse(value?.toString() ?? '') ?? 0;
}

class DatePlanResult {
  const DatePlanResult({
    required this.matchId,
    required this.center,
    required this.venues,
  });

  final int matchId;
  final LatLng center;
  final List<DatePlanVenue> venues;
}

class DatePlanVenue {
  const DatePlanVenue({
    required this.name,
    required this.rating,
    required this.venueType,
    this.address,
    this.photoUrl,
    this.distanceMeters,
  });

  factory DatePlanVenue.fromJson(Map<String, dynamic> json) {
    return DatePlanVenue(
      name: json['name']?.toString() ?? 'Venue',
      rating: (json['rating'] as num?)?.toDouble() ?? 0,
      venueType: json['venue_type']?.toString() ?? 'venue',
      address: json['address']?.toString(),
      photoUrl: json['photo_url']?.toString(),
      distanceMeters: json['distance_meters'] is num ? (json['distance_meters'] as num).toInt() : int.tryParse(json['distance_meters']?.toString() ?? ''),
    );
  }

  final String name;
  final double rating;
  final String venueType;
  final String? address;
  final String? photoUrl;
  final int? distanceMeters;
}
