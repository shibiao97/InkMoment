const emptyStringMap = <String, dynamic>{};

Map<String, dynamic>? asStringMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, item) => MapEntry(key.toString(), item));
  }
  return null;
}

List<dynamic> asList(Object? value) {
  if (value is List) return value;
  return const [];
}
