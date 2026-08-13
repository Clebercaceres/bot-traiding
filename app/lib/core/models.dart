class UserModel {
  final int id;
  final String name;
  final String email;
  UserModel({required this.id, required this.name, required this.email});
  factory UserModel.fromJson(Map j) =>
      UserModel(id: j['id'], name: j['name'], email: j['email']);
}

class AccountModel {
  final int id;
  final String label;
  final int login;
  final String server;
  final String broker;
  final String? currency;
  final double? balance;
  final bool agentOnline;

  AccountModel({
    required this.id,
    required this.label,
    required this.login,
    required this.server,
    required this.broker,
    this.currency,
    this.balance,
    required this.agentOnline,
  });

  factory AccountModel.fromJson(Map j) => AccountModel(
        id: j['id'],
        label: j['label'] ?? '',
        login: j['login'] ?? 0,
        server: j['server'] ?? '',
        broker: j['broker'] ?? 'unknown',
        currency: j['currency'],
        balance: (j['balance'] as num?)?.toDouble(),
        agentOnline: j['agent_online'] ?? false,
      );
}

class StatsModel {
  final double? balance;
  final String? currency;
  final int tradesToday;
  final double pnlPct;
  final int consecutiveLosses;
  final bool stopped;
  final String? stoppedReason;
  final bool agentOnline;

  StatsModel({
    this.balance,
    this.currency,
    required this.tradesToday,
    required this.pnlPct,
    required this.consecutiveLosses,
    required this.stopped,
    this.stoppedReason,
    required this.agentOnline,
  });

  factory StatsModel.fromJson(Map j) => StatsModel(
        balance: (j['balance'] as num?)?.toDouble(),
        currency: j['currency'],
        tradesToday: j['trades_today'] ?? 0,
        pnlPct: (j['pnl_pct'] as num?)?.toDouble() ?? 0,
        consecutiveLosses: j['consecutive_losses'] ?? 0,
        stopped: j['stopped'] ?? false,
        stoppedReason: j['stopped_reason'],
        agentOnline: j['agent_online'] ?? false,
      );
}

class SignalModel {
  final int id;
  final int accountId;
  final String? timestamp;
  final String symbol;
  final String direction;
  final double? entryPrice;
  final double? sl;
  final double? tp;
  final double? lotSize;
  final double? rsiValue;
  final double? score;
  final String status;

  SignalModel({
    required this.id,
    required this.accountId,
    this.timestamp,
    required this.symbol,
    required this.direction,
    this.entryPrice,
    this.sl,
    this.tp,
    this.lotSize,
    this.rsiValue,
    this.score,
    required this.status,
  });

  factory SignalModel.fromJson(Map j) => SignalModel(
        id: j['id'],
        accountId: j['account_id'] ?? 0,
        timestamp: j['timestamp'],
        symbol: j['symbol'] ?? '',
        direction: j['direction'] ?? '',
        entryPrice: (j['entry_price'] as num?)?.toDouble(),
        sl: (j['sl'] as num?)?.toDouble(),
        tp: (j['tp'] as num?)?.toDouble(),
        lotSize: (j['lot_size'] as num?)?.toDouble(),
        rsiValue: (j['rsi_value'] as num?)?.toDouble(),
        score: (j['score'] as num?)?.toDouble(),
        status: j['status'] ?? '',
      );
}

class TradeModel {
  final int id;
  final String symbol;
  final String direction;
  final String? openTime;
  final String? closeTime;
  final double? openPrice;
  final double? closePrice;
  final double? profit;
  final String? result;

  TradeModel({
    required this.id,
    required this.symbol,
    required this.direction,
    this.openTime,
    this.closeTime,
    this.openPrice,
    this.closePrice,
    this.profit,
    this.result,
  });

  factory TradeModel.fromJson(Map j) => TradeModel(
        id: j['id'],
        symbol: j['symbol'] ?? '',
        direction: j['direction'] ?? '',
        openTime: j['open_time'],
        closeTime: j['close_time'],
        openPrice: (j['open_price'] as num?)?.toDouble(),
        closePrice: (j['close_price'] as num?)?.toDouble(),
        profit: (j['profit'] as num?)?.toDouble(),
        result: j['result'],
      );
}

class ReportModel {
  final int totalTrades;
  final int wins;
  final int losses;
  final double winRate;
  final double totalPnl;
  final List<TradeModel> trades;
  final List<Map<String, dynamic>> pnlCurve;

  ReportModel({
    required this.totalTrades,
    required this.wins,
    required this.losses,
    required this.winRate,
    required this.totalPnl,
    required this.trades,
    required this.pnlCurve,
  });

  factory ReportModel.fromJson(Map j) {
    final s = j['summary'] as Map? ?? {};
    return ReportModel(
      totalTrades: s['total_trades'] ?? 0,
      wins: s['wins'] ?? 0,
      losses: s['losses'] ?? 0,
      winRate: (s['win_rate'] as num?)?.toDouble() ?? 0,
      totalPnl: (s['total_pnl'] as num?)?.toDouble() ?? 0,
      trades: (j['trades'] as List? ?? [])
          .map((t) => TradeModel.fromJson(t))
          .toList(),
      pnlCurve: (j['pnl_curve'] as List? ?? [])
          .map((p) => Map<String, dynamic>.from(p))
          .toList(),
    );
  }
}
