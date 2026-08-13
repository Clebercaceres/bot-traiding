import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/api_client.dart';
import '../core/models.dart';

class AccountsTab extends StatefulWidget {
  final int? activeAccountId;
  final void Function(int?) onAccountSelected;
  const AccountsTab({super.key, this.activeAccountId, required this.onAccountSelected});
  @override
  State<AccountsTab> createState() => _AccountsTabState();
}

class _AccountsTabState extends State<AccountsTab> {
  List<AccountModel> _accounts = [];
  List<Map<String, dynamic>> _servers = [];
  bool _loading = true;
  bool _adding  = false;

  final _serverCtrl = TextEditingController();
  final _loginCtrl  = TextEditingController();
  final _passCtrl   = TextEditingController();
  final _labelCtrl  = TextEditingController();
  String? _selectedServer;
  bool _obscurePass = true;

  static const _card   = Color(0xFF1c2133);
  static const _card2  = Color(0xFF232a3e);
  static const _border = Color(0xFF2a3050);
  static const _txt2   = Color(0xFF8893b4);
  static const _txt3   = Color(0xFF5b6480);
  static const _green  = Color(0xFF22c55e);
  static const _red    = Color(0xFFef4444);
  static const _accent = Color(0xFF5046e4);
  static const _blue   = Color(0xFF3b82f6);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final ra = await api.get('/api/accounts');
    final rs = await api.get('/api/accounts/servers');
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (api.isOk(ra)) {
        _accounts = (ra.data as List).map((j) => AccountModel.fromJson(j)).toList();
      }
      if (api.isOk(rs)) {
        _servers = (rs.data as List).map((j) => Map<String, dynamic>.from(j)).toList();
      }
    });
  }

  Future<void> _addAccount() async {
    final server = _selectedServer ?? _serverCtrl.text.trim();
    final loginTxt = _loginCtrl.text.trim();
    final pass  = _passCtrl.text.trim();
    final label = _labelCtrl.text.trim();
    if (server.isEmpty || loginTxt.isEmpty || pass.isEmpty) {
      _snack('Completa servidor, login y contraseña', _red);
      return;
    }
    final login = int.tryParse(loginTxt);
    if (login == null) { _snack('Login debe ser un número', _red); return; }

    setState(() => _adding = true);
    final r = await api.post('/api/accounts', data: {
      'label': label.isEmpty ? 'Cuenta $login' : label,
      'login': login,
      'password': pass,
      'server': server,
    });
    setState(() => _adding = false);
    if (!mounted) return;
    if (api.isOk(r)) {
      _snack('Cuenta guardada ✓', _green);
      _loginCtrl.clear(); _passCtrl.clear(); _labelCtrl.clear();
      setState(() => _selectedServer = null);
      await _load();
      final id = r.data['account_id'];
      if (id != null) widget.onAccountSelected(id);
    } else {
      _snack(api.errorMsg(r), _red);
    }
  }

  Future<void> _deleteAccount(AccountModel a) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: _card,
        title: const Text('Eliminar cuenta', style: TextStyle(color: Color(0xFFe8eaf6))),
        content: Text('¿Eliminar "${a.label}"? Se borrarán todas sus señales y trades.',
            style: const TextStyle(color: _txt2)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar', style: TextStyle(color: _txt2))),
          TextButton(onPressed: () => Navigator.pop(context, true),
              child: const Text('Eliminar', style: TextStyle(color: _red))),
        ],
      ),
    );
    if (ok != true) return;
    final r = await api.delete('/api/accounts/${a.id}');
    if (!mounted) return;
    if (api.isOk(r)) {
      _snack('Cuenta eliminada', _txt2);
      if (widget.activeAccountId == a.id) widget.onAccountSelected(null);
      await _load();
    } else {
      _snack(api.errorMsg(r), _red);
    }
  }

  void _showEnvGuide(AccountModel a) {
    final origin = 'http://TU-SERVIDOR.railway.app';
    showModalBottomSheet(
      context: context,
      backgroundColor: _card,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (_) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Configurar agente (.env)',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700,
                  color: Color(0xFFe8eaf6))),
          const SizedBox(height: 4),
          const Text('Copia esto en tu archivo agent/.env',
              style: TextStyle(color: _txt2, fontSize: 12)),
          const SizedBox(height: 14),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(color: _card2, borderRadius: BorderRadius.circular(10)),
            child: Text(
              'SERVER_URL=$origin\n'
              'TB_EMAIL=tu@email.com\n'
              'TB_PASSWORD=tu_contraseña\n'
              'ACCOUNT_ID=${a.id}\n'
              'MT5_LOGIN=${a.login}\n'
              'MT5_PASSWORD=tu_clave_mt5\n'
              'MT5_SERVER=${a.server}',
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12,
                  color: Color(0xFF8893b4), height: 1.7),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                  foregroundColor: _accent, side: const BorderSide(color: _accent)),
              icon: const Icon(Icons.copy, size: 16),
              label: const Text('Copiar'),
              onPressed: () {
                Clipboard.setData(ClipboardData(
                  text: 'SERVER_URL=$origin\n'
                      'TB_EMAIL=tu@email.com\n'
                      'TB_PASSWORD=tu_contraseña\n'
                      'ACCOUNT_ID=${a.id}\n'
                      'MT5_LOGIN=${a.login}\n'
                      'MT5_PASSWORD=tu_clave_mt5\n'
                      'MT5_SERVER=${a.server}',
                ));
                Navigator.pop(context);
                _snack('Copiado ✓', _green);
              },
            ),
          ),
          const SizedBox(height: 8),
        ]),
      ),
    );
  }

  void _snack(String msg, Color c) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg, style: TextStyle(color: c)),
      backgroundColor: _card, duration: const Duration(seconds: 2)));
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator(color: _accent));
    return RefreshIndicator(
      color: _accent,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Mis cuentas MT5',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700,
                  color: Color(0xFFe8eaf6))),
          const SizedBox(height: 12),
          if (_accounts.isEmpty)
            Container(
              padding: const EdgeInsets.all(32),
              decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12)),
              child: const Column(children: [
                Text('🔗', style: TextStyle(fontSize: 32)),
                SizedBox(height: 8),
                Text('Sin cuentas guardadas',
                    style: TextStyle(color: _txt3, fontSize: 14)),
              ]),
            )
          else
            ..._accounts.map((a) => _accountCard(a)),

          const SizedBox(height: 24),

          // Add account form
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12),
                border: Border.all(color: _border)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Agregar cuenta MT5',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700,
                      color: Color(0xFFe8eaf6))),
              const SizedBox(height: 16),

              // Server dropdown
              const Text('Servidor', style: TextStyle(color: _txt3, fontSize: 11,
                  fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF0f1117),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: _border),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: _selectedServer,
                    dropdownColor: _card,
                    style: const TextStyle(color: Color(0xFFe8eaf6), fontSize: 14),
                    hint: const Text('Seleccionar servidor…', style: TextStyle(color: _txt2)),
                    isExpanded: true,
                    items: [
                      ..._servers.map((s) => DropdownMenuItem(
                        value: s['name']?.toString(),
                        child: Text('${s['label']} (${s['name']})'),
                      )),
                      const DropdownMenuItem(value: '', child: Text('Otro…')),
                    ],
                    onChanged: (v) => setState(() => _selectedServer = v),
                  ),
                ),
              ),
              if (_selectedServer == '') ...[
                const SizedBox(height: 10),
                TextField(
                  controller: _serverCtrl,
                  decoration: const InputDecoration(labelText: 'Nombre del servidor'),
                ),
              ],
              const SizedBox(height: 12),
              TextField(
                controller: _loginCtrl,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Login (número)'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _passCtrl,
                obscureText: _obscurePass,
                decoration: InputDecoration(
                  labelText: 'Contraseña MT5',
                  suffixIcon: IconButton(
                    icon: Icon(_obscurePass ? Icons.visibility_off : Icons.visibility,
                        color: _txt2),
                    onPressed: () => setState(() => _obscurePass = !_obscurePass),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _labelCtrl,
                decoration: const InputDecoration(
                    labelText: 'Etiqueta (opcional)',
                    hintText: 'Ej: Mi cuenta Deriv Demo'),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _adding ? null : _addAccount,
                  child: _adding
                      ? const SizedBox(height: 20, width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Text('Guardar cuenta'),
                ),
              ),
            ]),
          ),
        ],
      ),
    );
  }

  Widget _accountCard(AccountModel a) {
    final isActive = a.id == widget.activeAccountId;
    final broker = a.broker;
    final icon = broker == 'bridge' ? '🔵' : broker == 'deriv' ? '🟢' : '⚪';
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: isActive ? _accent : _border, width: isActive ? 1.5 : 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(icon, style: const TextStyle(fontSize: 22)),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(a.label, style: const TextStyle(fontWeight: FontWeight.w700,
                fontSize: 14, color: Color(0xFFe8eaf6))),
            Text('Login: ${a.login} · ${a.server}',
                style: const TextStyle(color: _txt2, fontSize: 12)),
          ])),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Row(children: [
              Container(
                width: 7, height: 7,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: a.agentOnline ? _green : _txt3,
                ),
              ),
              const SizedBox(width: 5),
              Text(a.agentOnline ? 'Online' : 'Offline',
                  style: TextStyle(color: a.agentOnline ? _green : _txt3, fontSize: 11)),
            ]),
            const SizedBox(height: 2),
            Text('ID: ${a.id}', style: const TextStyle(color: _txt3, fontSize: 11)),
          ]),
        ]),
        if (a.balance != null) ...[
          const SizedBox(height: 8),
          Text('Balance: ${a.balance!.toStringAsFixed(2)} ${a.currency ?? ''}',
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800,
                  color: Color(0xFFe8eaf6))),
        ],
        const SizedBox(height: 12),
        Row(children: [
          if (!isActive)
            Expanded(child: OutlinedButton(
              style: OutlinedButton.styleFrom(
                  foregroundColor: _accent,
                  side: const BorderSide(color: _accent),
                  padding: const EdgeInsets.symmetric(vertical: 8)),
              onPressed: () => widget.onAccountSelected(a.id),
              child: const Text('Seleccionar', style: TextStyle(fontSize: 13)),
            ))
          else
            Expanded(child: Container(
              padding: const EdgeInsets.symmetric(vertical: 8),
              decoration: BoxDecoration(
                color: _accent.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: _accent.withOpacity(0.3)),
              ),
              child: const Center(child: Text('✓ Cuenta activa',
                  style: TextStyle(color: _accent, fontSize: 13, fontWeight: FontWeight.w600))),
            )),
          const SizedBox(width: 8),
          IconButton(
            style: IconButton.styleFrom(
                backgroundColor: _card2, shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8))),
            icon: const Icon(Icons.code, color: _txt2, size: 18),
            tooltip: 'Ver .env para agente',
            onPressed: () => _showEnvGuide(a),
          ),
          const SizedBox(width: 4),
          IconButton(
            style: IconButton.styleFrom(
                backgroundColor: _red.withOpacity(0.1), shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8))),
            icon: const Icon(Icons.delete_outline, color: _red, size: 18),
            onPressed: () => _deleteAccount(a),
          ),
        ]),
      ]),
    );
  }
}
