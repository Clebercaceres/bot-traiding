import 'package:flutter/material.dart';
import '../core/api_client.dart';

class ControlTab extends StatefulWidget {
  final int? accountId;
  const ControlTab({super.key, this.accountId});
  @override
  State<ControlTab> createState() => _ControlTabState();
}

class _ControlTabState extends State<ControlTab> {
  bool _analysis = false;
  bool _trading  = false;
  bool _auto     = false;
  bool _sending  = false;

  static const _card   = Color(0xFF1c2133);
  static const _border = Color(0xFF2a3050);
  static const _txt2   = Color(0xFF8893b4);
  static const _txt3   = Color(0xFF5b6480);
  static const _green  = Color(0xFF22c55e);
  static const _red    = Color(0xFFef4444);
  static const _accent = Color(0xFF5046e4);

  Future<void> _sendCmd(String cmd, bool newVal, void Function(bool) setter) async {
    if (widget.accountId == null) {
      _snack('Selecciona una cuenta primero', _red);
      return;
    }
    setState(() => _sending = true);
    final r = await api.post('/api/accounts/${widget.accountId}/command?command=$cmd');
    setState(() => _sending = false);
    if (!mounted) return;
    if (api.isOk(r)) {
      setState(() => setter(newVal));
      _snack('Comando enviado: $cmd', _green);
    } else {
      _snack(api.errorMsg(r), _red);
    }
  }

  void _snack(String msg, Color c) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg, style: TextStyle(color: c)),
      backgroundColor: _card, duration: const Duration(seconds: 2)));
  }

  @override
  Widget build(BuildContext context) {
    final noAccount = widget.accountId == null;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (noAccount)
          Container(
            padding: const EdgeInsets.all(14),
            margin: const EdgeInsets.only(bottom: 16),
            decoration: BoxDecoration(
              color: _red.withOpacity(0.1),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: _red.withOpacity(0.3)),
            ),
            child: const Text('⚠️ Selecciona una cuenta en la pestaña Inicio',
                style: TextStyle(color: _txt2, fontSize: 13)),
          ),

        _controlCard(
          icon: '🔍',
          title: 'Análisis M1/M15',
          description: 'El agente escanea señales continuamente en M1 y M15',
          value: _analysis,
          onChanged: noAccount || _sending ? null : (v) =>
              _sendCmd(v ? 'analysis_start' : 'analysis_stop', v, (x) => _analysis = x),
        ),
        const SizedBox(height: 12),
        _controlCard(
          icon: '💹',
          title: 'Ejecutar trades',
          description: 'Permite al agente abrir posiciones reales en MT5',
          value: _trading,
          onChanged: noAccount || _sending ? null : (v) =>
              _sendCmd(v ? 'trading_start' : 'trading_stop', v, (x) => _trading = x),
        ),
        const SizedBox(height: 12),
        _controlCard(
          icon: '🤖',
          title: 'Modo automático',
          description: 'ON: ejecuta señales sin confirmación\nOFF: señales aparecen para confirmar manualmente',
          value: _auto,
          onChanged: noAccount || _sending ? null : (v) =>
              _sendCmd(v ? 'set_auto_true' : 'set_auto_false', v, (x) => _auto = x),
        ),
        const SizedBox(height: 28),

        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12),
              border: Border.all(color: _border)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('ℹ️ Cómo funciona',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700,
                    color: Color(0xFFe8eaf6))),
            const SizedBox(height: 12),
            _infoRow('1.', 'Activa Análisis → el agente empieza a escanear'),
            _infoRow('2.', 'Activa Trading → permite abrir posiciones'),
            _infoRow('3.', 'Modo manual: confirmas cada señal en la pestaña Señales'),
            _infoRow('4.', 'Modo auto: el bot ejecuta directo (⚠️ precaución)'),
          ]),
        ),

        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12),
              border: Border.all(color: _border)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Símbolos activos',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700,
                    color: Color(0xFFe8eaf6))),
            const SizedBox(height: 8),
            const Text('Se detectan automáticamente según el broker conectado',
                style: TextStyle(color: _txt2, fontSize: 12)),
            const SizedBox(height: 12),
            _brokerChips('Bridge Markets', ['BullX500', 'BearX500', 'BullX777', 'BearX777', 'BullX1000', 'BearX1000'], const Color(0xFF3b82f6)),
            const SizedBox(height: 8),
            _brokerChips('Deriv', ['Volatility 75 Index'], _green),
          ]),
        ),
      ],
    );
  }

  Widget _controlCard({
    required String icon,
    required String title,
    required String description,
    required bool value,
    required void Function(bool)? onChanged,
  }) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12),
          border: Border.all(color: _border)),
      child: Row(children: [
        Text(icon, style: const TextStyle(fontSize: 22)),
        const SizedBox(width: 14),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700,
              color: Color(0xFFe8eaf6))),
          const SizedBox(height: 4),
          Text(description, style: const TextStyle(color: _txt2, fontSize: 12, height: 1.4)),
        ])),
        const SizedBox(width: 12),
        Switch(
          value: value,
          onChanged: onChanged,
          activeColor: _accent,
          inactiveTrackColor: _border,
        ),
      ]),
    );
  }

  Widget _infoRow(String num, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(num, style: const TextStyle(color: _accent, fontWeight: FontWeight.w700,
            fontSize: 13)),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: const TextStyle(color: _txt2, fontSize: 13))),
      ]),
    );
  }

  Widget _brokerChips(String label, List<String> symbols, Color color) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
      const SizedBox(height: 6),
      Wrap(spacing: 6, runSpacing: 6,
          children: symbols.map((s) => Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: color.withOpacity(0.1),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: color.withOpacity(0.3)),
            ),
            child: Text(s, style: TextStyle(color: color, fontSize: 11,
                fontWeight: FontWeight.w600)),
          )).toList()),
    ]);
  }
}
