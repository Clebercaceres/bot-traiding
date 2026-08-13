import 'package:flutter/foundation.dart';
import 'api_client.dart';
import 'models.dart';

class AuthProvider extends ChangeNotifier {
  UserModel? _user;
  bool _loading = false;

  UserModel? get user => _user;
  bool get loading => _loading;
  bool get isLoggedIn => _user != null;

  Future<void> checkAuth() async {
    final r = await api.get('/api/auth/me');
    if (api.isOk(r)) {
      _user = UserModel.fromJson(r.data);
      notifyListeners();
    }
  }

  Future<String?> login(String email, String password) async {
    _loading = true;
    notifyListeners();
    final r = await api.post('/api/auth/login',
        data: {'email': email, 'password': password});
    _loading = false;
    if (api.isOk(r)) {
      await checkAuth();
      return null;
    }
    notifyListeners();
    return api.errorMsg(r);
  }

  Future<String?> register(String name, String email, String password) async {
    _loading = true;
    notifyListeners();
    final r = await api.post('/api/auth/register',
        data: {'name': name, 'email': email, 'password': password});
    _loading = false;
    if (api.isOk(r)) {
      await checkAuth();
      return null;
    }
    notifyListeners();
    return api.errorMsg(r);
  }

  Future<void> logout() async {
    await api.post('/api/auth/logout');
    _user = null;
    notifyListeners();
  }
}
