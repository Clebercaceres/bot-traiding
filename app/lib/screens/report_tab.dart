import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../core/api_client.dart';
import '../core/models.dart';

class ReportTab extends StatefulWidget {
  final int? accountId;
  const ReportTab({super.key, this.accountId});
  @override
  State<ReportTab> createState() => _ReportTabState();
}

class _ReportTabState extends State<ReportTab> {
  ReportModel? _report;
  int _days = 7;
  bool _loading = true;

  static const _card   = Color(0xFF1c2133);
  static const _card2  = Color(0xFF232a3e);
  static const _border = Color(0xFF2a3050);
  static const _txt2   = Color(0xFF8893b4);
  static const _txt3   = Color(0xFF5b6480);
  static const _green  = Color(0xFF22c55e);
  static const _red    = Color(0xFFef4444);
  static const _accent = Color(0xFF5046e4);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final q = StringBuffer('?days=$_days');
    if (widget.accountId != null) q.write('&account_id=${widget.accountId}');
    final r = await api.get('/api/report$q');
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (api.isOk(r)) _report = ReportModel.fromJson(r.data);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      // Filter bar
      Container(
        color: const Color(0xFF161b27),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(children: [
          const Text('Período: ', style: TextStyle(color: _txt2, fontSize: 13)),
          const Spacer(),
          ...[7, 30, 90].map((d) => Padding(
            padding: const EdgeInsets.only(left: 6),
            child: GestureDetector(
              onTap: () { setState(() => _days = d); _load(); },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                decoration: BoxDecoration(
                  color: _days == d ? _accent : Colors.transparent,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: _days == d ? _accent : _border),
                ),
                child: Text('${d}d',
                    style: TextStyle(
                        color: _days == d ? Colors.white : _txt2,
                        fontSize: 12, fontWeight: FontWeight.w600)),
              ),
            ),
          )),
        ]),
      ),
      Expanded(
        child: _loading
            ? const Center(child: CircularProgressIndicator(color: _accent))
            : RefreshIndicator(
                color: _accent,
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    _summaryGrid(),
                    const SizedBox(height: 16),
                    _chartCard(),
                    const SizedBox(height: 16),
                    _tradeList(),
                  ],
                ),
              ),
      ),
    ]);
  }

  Widget _summaryGrid() {
    final r = _report;
    if (r == null) return const SizedBox.shrink();
    final pnl = r.totalPnl;
    return GridView.count(
      crossAxisCount: 3,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 10,
      mainAxisSpacing: 10,
      childAspectRatio: 1.3,
      children: [
        _repCard('Trades', '${r.totalTrades}', null),
        _repCard('Wins', '${r.wins}', _green),
        _repCard('Losses', '${r.losses}', _red),
        _repCard('Win rate', '${r.winRate.toStringAsFixed(1)}%', null),
        _repCard('PnL',
            '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(2)}',
            pnl >= 0 ? _green : _red),
        _repCard('Días', '$_days', null),
      ],
    );
  }

  Widget _repCard(String label, String value, Color? color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
          color: _card2, borderRadius: BorderRadius.circular(10)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: const TextStyle(color: _txt3, fontSize: 10,
            fontWeight: FontWeight.w700)),
        const Spacer(),
        Text(value,
            style: TextStyle(
                color: color ?? const Color(0xFFe8eaf6),
                fontSize: 18, fontWeight: FontWeight.w800)),
      ]),
    );
  }

  Widget _chartCard() {
    final curve = _report?.pnlCurve ?? [];
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12),
          border: Border.all(color: _border)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Curva PnL acumulado',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700,
                color: Color(0xFFe8eaf6))),
        const SizedBox(height: 16),
        SizedBox(
          height: 140,
          child: curve.isEmpty
              ? const Center(child: Text('Sin datos', style: TextStyle(color: _txt3)))
              : _buildChart(curve),
        ),
      ]),
    );
  }

  Widget _buildChart(List<Map<String, dynamic>> curve) {
    final spots = <FlSpot>[];
    for (int i = 0; i < curve.length; i++) {
      final y = (curve[i]['pnl'] as num?)?.toDouble() ?? 0;
      spots.add(FlSpot(i.toDouble(), y));
    }
    final vals = spots.map((s) => s.y).toList();
    final minY = vals.reduce((a, b) => a < b ? a : b);
    final maxY = vals.reduce((a, b) => a > b ? a : b);
    final last = vals.last;
    final lineColor = last >= 0 ? _green : _red;

    return LineChart(LineChartData(
      minY: minY < 0 ? minY * 1.1 : minY * 0.9,
      maxY: maxY > 0 ? maxY * 1.1 : maxY * 0.9,
      gridData: FlGridData(
        drawHorizontalLine: true,
        drawVerticalLine: false,
        getDrawingHorizontalLine: (_) => FlLine(color: _border, strokeWidth: 1),
      ),
      borderData: FlBorderData(show: false),
      titlesData: FlTitlesData(
        leftTitles: AxisTitles(sideTitles: SideTitles(
          showTitles: true, reservedSize: 40,
          getTitlesWidget: (v, _) => Text(v.toStringAsFixed(1),
              style: const TextStyle(color: _txt3, fontSize: 9)),
        )),
        bottomTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
      ),
      lineBarsData: [LineChartBarData(
        spots: spots,
        isCurved: true,
        color: lineColor,
        barWidth: 2.5,
        dotData: FlDotData(
          show: true,
          getDotPainter: (s, _, __, i) => i == spots.length - 1
              ? FlDotCirclePainter(radius: 4, color: lineColor, strokeWidth: 0)
              : FlDotCirclePainter(radius: 0, color: Colors.transparent, strokeWidth: 0),
        ),
        belowBarData: BarAreaData(
          show: true,
          color: lineColor.withOpacity(0.08),
        ),
      )],
    ));
  }

  Widget _tradeList() {
    final trades = _report?.trades ?? [];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Historial de trades',
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700,
              color: Color(0xFFe8eaf6))),
      const SizedBox(height: 12),
      if (trades.isEmpty)
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(12)),
          child: const Center(child: Text('Sin trades cerrados',
              style: TextStyle(color: _txt3))),
        )
      else
        ...trades.map((t) => _tradeRow(t)),
    ]);
  }

  Widget _tradeRow(TradeModel t) {
    final isWin = t.result == 'win';
    final profit = t.profit ?? 0;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(10),
          border: Border.all(color: _border)),
      child: Row(children: [
        Container(
          width: 28, height: 28,
          decoration: BoxDecoration(
            color: (isWin ? _green : _red).withOpacity(0.15),
            borderRadius: BorderRadius.circular(6)),
          child: Center(child: Text(t.direction == 'buy' ? '▲' : '▼',
              style: TextStyle(color: t.direction == 'buy' ? _green : _red, fontSize: 12))),
        ),
        const SizedBox(width: 10),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(t.symbol, style: const TextStyle(fontWeight: FontWeight.w700,
              fontSize: 13, color: Color(0xFFe8eaf6))),
          Text(t.closeTime?.substring(0, 16).replaceAll('T', ' ') ?? '—',
              style: const TextStyle(color: _txt3, fontSize: 11)),
        ])),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
          decoration: BoxDecoration(
            color: (isWin ? _green : _red).withOpacity(0.15),
            borderRadius: BorderRadius.circular(20)),
          child: Text(t.result ?? '—',
              style: TextStyle(color: isWin ? _green : _red,
                  fontSize: 11, fontWeight: FontWeight.w700)),
        ),
        const SizedBox(width: 10),
        Text('${profit >= 0 ? '+' : ''}${profit.toStringAsFixed(2)}',
            style: TextStyle(color: isWin ? _green : _red,
                fontWeight: FontWeight.w700, fontSize: 14)),
      ]),
    );
  }
}
