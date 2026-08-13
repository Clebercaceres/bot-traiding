import 'package:flutter/material.dart';
import '../core/api_client.dart';
import '../core/models.dart';

class SignalsTab extends StatefulWidget {
  final int? accountId;
  const SignalsTab({super.key, this.accountId});
  @override
  State<SignalsTab> createState() => _SignalsTabState();
}

class _SignalsTabState extends State<SignalsTab> with SingleTickerProviderStateMixin {
  late TabController _tabs;
  List<SignalModel> _pending = [];
  List<SignalModel> _history = [];
  bool _loadingP = true, _loadingH = true;

  static const _card   = Color(0xFF1c2133);
  static const _card2  = Color(0xFF232a3e);
  static const _border = Color(0xFF2a3050);
  static const _txt2   = Color(0xFF8893b4);
  static const _txt3   = Color(0xFF5b6480);
  static const _green  = Color(0xFF22c55e);
  static const _red    = Color(0xFFef4444);
  static const _yellow = Color(0xFFf59e0b);
  static const _accent = Color(0xFF5046e4);

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _loadPending();
    _loadHistory();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _loadPending() async {
    final r = await api.get('/api/signals/pending');
    if (!mounted) return;
    setState(() {
      _loadingP = false;
      if (api.isOk(r)) _pending = (r.data as List).map((j) => SignalModel.fromJson(j)).toList();
    });
  }

  Future<void> _loadHistory() async {
    final q = widget.accountId != null
        ? '?account_id=${widget.accountId}&limit=50'
        : '?limit=50';
    final r = await api.get('/api/signals/history$q');
    if (!mounted) return;
    setState(() {
      _loadingH = false;
      if (api.isOk(r)) _history = (r.data as List).map((j) => SignalModel.fromJson(j)).toList();
    });
  }

  Future<void> _confirmSig(int id) async {
    final r = await api.post('/api/signals/$id/confirm');
    if (!mounted) return;
    if (api.isOk(r)) { _showSnack('Confirmada ✓', _green); _loadPending(); }
    else _showSnack(api.errorMsg(r), _red);
  }

  Future<void> _rejectSig(int id) async {
    final r = await api.post('/api/signals/$id/reject');
    if (!mounted) return;
    if (api.isOk(r)) { _showSnack('Rechazada', _txt2); _loadPending(); }
  }

  void _showSnack(String msg, Color c) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg, style: TextStyle(color: c)),
      backgroundColor: _card, duration: const Duration(seconds: 2)));
  }

  Color _statusColor(String s) {
    switch (s) {
      case 'pending': return _yellow;
      case 'executed': case 'closed': return _green;
      case 'rejected': return _red;
      default: return _txt2;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Container(
        color: const Color(0xFF161b27),
        child: TabBar(
          controller: _tabs,
          labelColor: _accent,
          unselectedLabelColor: _txt2,
          indicatorColor: _accent,
          tabs: [
            Tab(text: 'Pendientes${_pending.isNotEmpty ? ' (${_pending.length})' : ''}'),
            const Tab(text: 'Historial'),
          ],
        ),
      ),
      Expanded(
        child: TabBarView(controller: _tabs, children: [
          // Pendientes
          _loadingP
              ? const Center(child: CircularProgressIndicator(color: _accent))
              : RefreshIndicator(
                  color: _accent,
                  onRefresh: _loadPending,
                  child: _pending.isEmpty
                      ? ListView(children: const [
                          SizedBox(height: 80),
                          Center(child: Column(children: [
                            Text('✅', style: TextStyle(fontSize: 32)),
                            SizedBox(height: 8),
                            Text('Sin señales pendientes',
                                style: TextStyle(color: _txt3, fontSize: 14)),
                          ])),
                        ])
                      : ListView.builder(
                          padding: const EdgeInsets.all(16),
                          itemCount: _pending.length,
                          itemBuilder: (_, i) => _pendingCard(_pending[i]),
                        ),
                ),
          // Historial
          _loadingH
              ? const Center(child: CircularProgressIndicator(color: _accent))
              : RefreshIndicator(
                  color: _accent,
                  onRefresh: _loadHistory,
                  child: _history.isEmpty
                      ? ListView(children: const [
                          SizedBox(height: 80),
                          Center(child: Text('Sin historial',
                              style: TextStyle(color: _txt3, fontSize: 14))),
                        ])
                      : ListView.builder(
                          padding: const EdgeInsets.all(16),
                          itemCount: _history.length,
                          itemBuilder: (_, i) => _historyRow(_history[i]),
                        ),
                ),
        ]),
      ),
    ]);
  }

  Widget _pendingCard(SignalModel s) {
    final isBuy = s.direction == 'buy';
    final dirColor = isBuy ? _green : _red;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12),
          border: Border.all(color: _border)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            width: 32, height: 32,
            decoration: BoxDecoration(color: dirColor.withOpacity(0.15),
                borderRadius: BorderRadius.circular(7)),
            child: Center(child: Text(isBuy ? '▲' : '▼',
                style: TextStyle(color: dirColor, fontSize: 14))),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(s.symbol,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14,
                  color: Color(0xFFe8eaf6)))),
          Text('Score: ${s.score?.toStringAsFixed(0) ?? '—'}',
              style: const TextStyle(color: _txt2, fontSize: 12)),
        ]),
        const SizedBox(height: 10),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          _mini('SL', s.sl, _red),
          _mini('TP', s.tp, _green),
          _mini('RSI', s.rsiValue, null),
          _mini('Lot', s.lotSize, null),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: _green,
                padding: const EdgeInsets.symmetric(vertical: 9)),
            onPressed: () => _confirmSig(s.id),
            child: const Text('✓ Confirmar', style: TextStyle(fontSize: 13)),
          )),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton(
            style: OutlinedButton.styleFrom(foregroundColor: _txt2,
                side: const BorderSide(color: _border),
                padding: const EdgeInsets.symmetric(vertical: 9)),
            onPressed: () => _rejectSig(s.id),
            child: const Text('✗ Rechazar', style: TextStyle(fontSize: 13)),
          )),
        ]),
      ]),
    );
  }

  Widget _historyRow(SignalModel s) {
    final isBuy = s.direction == 'buy';
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(10),
          border: Border.all(color: _border)),
      child: Row(children: [
        Container(
          width: 28, height: 28,
          decoration: BoxDecoration(
            color: (isBuy ? _green : _red).withOpacity(0.15),
            borderRadius: BorderRadius.circular(6)),
          child: Center(child: Text(isBuy ? '▲' : '▼',
              style: TextStyle(color: isBuy ? _green : _red, fontSize: 12))),
        ),
        const SizedBox(width: 10),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(s.symbol, style: const TextStyle(fontWeight: FontWeight.w700,
              fontSize: 13, color: Color(0xFFe8eaf6))),
          Text(s.timestamp?.substring(0, 16).replaceAll('T', ' ') ?? '—',
              style: const TextStyle(color: _txt3, fontSize: 11)),
        ])),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: _statusColor(s.status).withOpacity(0.15),
            borderRadius: BorderRadius.circular(20)),
          child: Text(s.status,
              style: TextStyle(color: _statusColor(s.status),
                  fontSize: 11, fontWeight: FontWeight.w700)),
        ),
        const SizedBox(width: 8),
        Text('${s.score?.toStringAsFixed(0) ?? '—'}',
            style: const TextStyle(color: _txt2, fontSize: 12)),
      ]),
    );
  }

  Widget _mini(String label, double? v, Color? color) {
    String val = '—';
    if (v != null) val = v > 100 ? v.toStringAsFixed(2) : v.toStringAsFixed(5);
    return Column(children: [
      Text(label, style: const TextStyle(color: _txt3, fontSize: 10, fontWeight: FontWeight.w600)),
      const SizedBox(height: 2),
      Text(val, style: TextStyle(color: color ?? _txt2, fontSize: 12, fontWeight: FontWeight.w600),
          maxLines: 1, overflow: TextOverflow.ellipsis),
    ]);
  }
}
