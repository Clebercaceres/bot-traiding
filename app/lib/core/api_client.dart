import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:cookie_jar/cookie_jar.dart';
import 'config.dart';

class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;

  late final Dio dio;
  final CookieJar cookieJar = CookieJar();

  ApiClient._internal() {
    dio = Dio(BaseOptions(
      baseUrl: AppConfig.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 15),
      headers: {'Content-Type': 'application/json'},
      validateStatus: (_) => true, // maneja 4xx/5xx sin throw
    ));
    dio.interceptors.add(CookieManager(cookieJar));
  }

  Future<Response> get(String path, {Map<String, dynamic>? params}) =>
      dio.get(path, queryParameters: params);

  Future<Response> post(String path, {dynamic data}) =>
      dio.post(path, data: data);

  Future<Response> delete(String path) => dio.delete(path);

  bool isOk(Response r) => r.statusCode != null && r.statusCode! < 400;

  String errorMsg(Response r) {
    final d = r.data;
    if (d is Map) return d['detail']?.toString() ?? 'Error ${r.statusCode}';
    return 'Error ${r.statusCode}';
  }
}

final api = ApiClient();
