import 'dart:io';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:cookie_jar/cookie_jar.dart';
import 'package:path_provider/path_provider.dart';
import '../constants.dart';

class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  late Dio dio;
  late Dio hardwareDio;
  late Dio webDio;
  late PersistCookieJar cookieJar;

  factory ApiClient() {
    return _instance;
  }

  ApiClient._internal() {
    dio = Dio(BaseOptions(
      baseUrl: userApiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 15),
    ));
    
    hardwareDio = Dio(BaseOptions(
      baseUrl: hardwareApiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 15),
    ));

    webDio = Dio(BaseOptions(
      baseUrl: 'https://waterlevel.pro',
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 15),
    ));
  }

  Future<void> init() async {
    Directory appDocDir = await getApplicationDocumentsDirectory();
    String appDocPath = appDocDir.path;
    cookieJar = PersistCookieJar(
      ignoreExpires: true,
      storage: FileStorage("$appDocPath/.cookies/"),
    );
    dio.interceptors.add(CookieManager(cookieJar));
  }

  // Auth Endpoints
  Future<Response> login(String email, String password, String recaptchaToken) async {
    return await dio.post('/login', data: {
      'email': email,
      'password': password,
      'recaptcha_token': recaptchaToken,
      'remember': true,
    });
  }

  Future<Response> register(String email, String password, String recaptchaToken) async {
    return await dio.post('/register', data: {
      'email': email,
      'password': password,
      'recaptcha_token': recaptchaToken,
    });
  }

  Future<Response> getMe() async {
    return await dio.get('/me');
  }

  Future<Response> logout() async {
    return await dio.post('/logout');
  }

  // Devices Endpoint
  Future<Response> getDevices() async {
    return await dio.get('/devices');
  }

  // Hardware API Endpoints
  Future<Response> getSensorData(String publicKey) async {
    return await hardwareDio.get('/sensor_view_api', queryParameters: {'public_key': publicKey});
  }

  Future<Response> getSensorDataExtended(String publicKey) async {
    return await webDio.get('/data-api', queryParameters: {'key': publicKey});
  }

  Future<Response> getRelayData(String publicKey) async {
    return await hardwareDio.get('/relay_view_api', queryParameters: {'public_key': publicKey});
  }

  Future<Response> toggleRelay(String publicKey, bool turnOn) async {
    final formData = FormData.fromMap({
      'public_key': publicKey,
      'action': turnOn ? 'on' : 'off',
    });
    return await hardwareDio.post('/relay_view_api', data: formData);
  }
}
