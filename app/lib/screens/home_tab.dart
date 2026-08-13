import 'package:flutter/material.dart';
import 'dart:async';
import '../core/api_client.dart';
import '../core/models.dart';

class HomeTab extends StatefulWidget {
  final int? accountId;
  final void Function(int?) onAccountChanged;
  const HomeTab({super.key, this.accountId, required this.onAccountChanged});
  @override
  State<HomeTab> createState() => _HomeTabState();
}

class _HomeTabState extends State<HomeTab> {
  StatsModel? _stats;
  List<SignalModel> _pending = [];
  List<AccountModel> _accounts = [];
  int? _selectedId;
  Timer? _timer;
  bool _loading = true;

  static const _card   = Color(0xFF1c2133);
  static const _border = Color(0xFF2a3050);
  static const _txt2   = Color(0xFF8893b4);
  static const _txt3   = Color(0xFF5b6480);
  static const _green  = Color(0xFF22c55e);
  static const _red    = Color(0xFFef4444);
  static const _accent = Color(0xFF5046e4);

  @override
  void initState() {
    super.initState();
    _selectedId = widget.accountId;
    _loadAccounts();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 15), (_) => _refresh());
  }

  @override
  void didUpdateWidget(HomeTab old) {
    super.didUpdateWidget(old);
    if (old.accountId != widget.accountId) {
      _selectedId = widget.accountId;
      _refresh();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _loadAccounts() async {
    final r = await api.get('/api/accounts');
    if (!mounted || !api.isOk(r)) return;
    final list = (r.data as List).map((j) => AccountModel.fromJson(j)).toList();
    setState(() {
      _accounts = list;
      if (_selectedId == null && list.isNotEmpty) {
        _selectedId = list.first.id;
        widget.onAccountChanged(_selectedId);
      }
    });
    _refresh();
  }

  Future<void> _refresh() async {
    final q = _selectedId != null ? '?account_id=$_selectedId' : '';
    final rs = await api.get('/api/stats$q');
    final rp = await api.get('/api/signals/pending');
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (api.isOk(rs)) _stats = StatsModel.fromJson(rs.data);
      if (api.isOk(rp)) {
        _pending = (rp.data as List).map((j) => SignalModel.fromJson(j)).toList();
      }
    });
  }

  Future<void> _confirmSig(int id) async {
    final r = await api.post('/api/signals/$id/confirm');
    if (!mounted) return;
    if (api.isOk(r)) {
      _showSnack('Señal confirmada ✓', _green);
      _refresh();
    } else {
      _showSnack(api.errorMsg(r), _red);
    }
  }

  Future<void> _rejectSig(int id) async {
    final r = await api.post('/api/signals/$id/reject');
    if (!mounted) return;
    if (api.isOk(r)) {
      _showSnack('Señal rechazada', _txt2);
      _refresh();
    }
  }

  void _showSnack(String msg, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg, style: TextStyle(color: color)),
      backgroundColor: _card,
      duration: const Duration(seconds: 2),
    ));
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator(color: _accent));
    return RefreshIndicator(
      color: _accent,
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Account selector
          if (_accounts.length > 1) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
              decoration: BoxDecoration(
                color: _card,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: _border),
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<int>(
                  value: _selectedId,
                  dropdownColor: _card,
                  style: const TextStyle(color: Color(0xFFe8eaf6), fontSize: 14),
                  hint: const Text('Seleccionar cuenta', style: TextStyle(color: _txt2)),
                  items: _accounts.map((a) => DropdownMenuItem(
                    value: a.id,
                    child: Text('${a.label} (${a.login})'),
                  )).toList(),
                  onChanged: (id) {
                    setState(() => _selectedId = id);
                    widget.onAccountChanged(id);
                    _refresh();
                  },
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],

          // Agent status
          if (_stats != null) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: _card,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                  color: _stats!.agentOnline ? _green.withOpacity(0.4) : _border,
                ),
              ),
              child: Row(children: [
                Container(
                  width: 8, height: 8,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _stats!.agentOnline ? _green : _txt3,
                    boxShadow: _stats!.agentOnline
                        ? [BoxShadow(color: _green.withOpacity(0.4), blurRadius: 6)]
                        : null,
                  ),
                ),
                const SizedBox(width: 10),
                Text(
                  _stats!.agentOnline ? 'Agente conectado' : 'Agente offline',
                  style: TextStyle(
                    color: _stats!.agentOnline ? _green : _txt2,
                    fontSize: 13, fontWeight: FontWeight.w600,
                  ),
                ),
              ]),
            ),
            const SizedBox(height: 16),
          ],

          // Stop banner
          if (_stats?.stopped == true) ...[
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: _red.withOpacity(0.1),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: _red.withOpacity(0.4)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('🚫 Bot detenido',
                    style: TextStyle(color: _red, fontWeight: FontWeight.w700)),
                if (_stats?.stoppedReason != null)
                  Text(_stats!.stoppedReason!,
                      style: const TextStyle(color: _txt2, fontSize: 12)),
              ]),
            ),
            const SizedBox(height: 16),
          ],

          // Stats grid
          if (_stats != null) ...[
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              childAspectRatio: 1.5,
              children: [
                _statCard('Balance',
                    _stats!.balance != null
                        ? '${_stats!.balance!.toStringAsFixed(2)} ${_stats!.currency ?? ''}'
                        : '—',
                    null),
                _statCard('Trades hoy', '${_stats!.tradesToday}', null),
                _statCard('PnL hoy',
                    '${_stats!.pnlPct >= 0 ? '+' : ''}${_stats!.pnlPct.toStringAsFixed(2)}%',
                    _stats!.pnlPct >= 0 ? _green : _red),
                _statCard('Pérd. consec.', '${_stats!.consecutiveLosses}', null),
              ],
            ),
            const SizedBox(height: 24),
          ],

          // Pending signals
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            const Text('Señales pendientes',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700,
                    color: Color(0xFFe8eaf6))),
            if (_pending.isNotEmpty)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: _accent, borderRadius: BorderRadius.circular(20)),
                child: Text('${_pending.length}',
                    style: const TextStyle(color: Colors.white, fontSize: 11,
                        fontWeight: FontWeight.w700)),
              ),
          ]),
          const SizedBox(height: 12),
          if (_pending.isEmpty)
            Container(
              padding: const EdgeInsets.all(32),
              decoration: BoxDecoration(
                  color: _card, borderRadius: BorderRadius.circular(12)),
              child: const Column(children: [
                Text('✅', style: TextStyle(fontSize: 28)),
                SizedBox(height: 8),
                Text('Sin señales pendientes',
                    style: TextStyle(color: _txt3, fontSize: 14)),
              ]),
            )
          else
            ..._pending.map((s) => _signalCard(s)),
        ],
      ),
    );
  }

  Widget _statCard(String label, String value, Color? valueColor) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: const TextStyle(color: _txt3, fontSize: 11,
            fontWeight: FontWeight.w600)),
        const Spacer(),
        Text(value,
            style: TextStyle(
                color: valueColor ?? const Color(0xFFe8eaf6),
                fontSize: 20, fontWeight: FontWeight.w800),
            maxLines: 1, overflow: TextOverflow.ellipsis),
      ]),
    );
  }

  Widget _signalCard(SignalModel s) {
    final isBuy = s.direction == 'buy';
    final dirColor = isBuy ? _green : _red;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            width: 36, height: 36,
            decoration: BoxDecoration(
              color: dirColor.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Center(
              child: Text(isBuy ? '▲' : '▼',
                  style: TextStyle(color: dirColor, fontSize: 16)),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(s.symbol, style: const TextStyle(fontWeight: FontWeight.w700,
                fontSize: 14, color: Color(0xFFe8eaf6))),
            Text('${s.direction.toUpperCase()} · Lot: ${s.lotSize?.toStringAsFixed(2) ?? '—'}',
                style: TextStyle(color: dirColor, fontSize: 12)),
          ])),
          Container(
            width: 44, height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: _accent, width: 2),
            ),
            child: Center(
              child: Text('${s.score?.toStringAsFixed(0) ?? '—'}',
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w800,
                      color: Color(0xFFe8eaf6))),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          _priceChip('Entrada', s.entryPrice, null),
          const SizedBox(width: 8),
          _priceChip('SL', s.sl, _red),
          const SizedBox(width: 8),
          _priceChip('TP', s.tp, _green),
          const SizedBox(width: 8),
          _priceChip('RSI', s.rsiValue, null),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                  backgroundColor: _green,
                  padding: const EdgeInsets.symmetric(vertical: 10)),
              onPressed: () => _confirmSig(s.id),
              child: const Text('✓ Confirmar',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: OutlinedButton(
              style: OutlinedButton.styleFrom(
                  foregroundColor: _txt2,
                  side: const BorderSide(color: _border),
                  padding: const EdgeInsets.symmetric(vertical: 10)),
              onPressed: () => _rejectSig(s.id),
              child: const Text('✗ Rechazar', style: TextStyle(fontSize: 13)),
            ),
          ),
        ]),
      ]),
    );
  }

  Widget _priceChip(String label, double? value, Color? color) {
    String display = '—';
    if (value != null) {
      display = value > 100 ? value.toStringAsFixed(2) : value.toStringAsFixed(5);
    }
    return Expanded(
      child: Column(children: [
        Text(label, style: const TextStyle(color: _txt3, fontSize: 10,
            fontWeight: FontWeight.w600)),
        const SizedBox(height: 2),
        Text(display, style: TextStyle(
            color: color ?? const Color(0xFFe8eaf6),
            fontSize: 12, fontWeight: FontWeight.w600),
            maxLines: 1, overflow: TextOverflow.ellipsis),
      ]),
    );
  }
}
