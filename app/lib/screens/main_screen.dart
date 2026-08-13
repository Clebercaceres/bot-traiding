import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/auth_provider.dart';
import 'home_tab.dart';
import 'signals_tab.dart';
import 'report_tab.dart';
import 'control_tab.dart';
import 'accounts_tab.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});
  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _idx = 0;
  int? _activeAccountId;

  void setActiveAccount(int? id) {
    setState(() => _activeAccountId = id);
  }

  static const _accent = Color(0xFF5046e4);
  static const _bg2    = Color(0xFF161b27);
  static const _border = Color(0xFF2a3050);
  static const _txt2   = Color(0xFF8893b4);

  @override
  Widget build(BuildContext context) {
    final tabs = [
      HomeTab(accountId: _activeAccountId, onAccountChanged: setActiveAccount),
      SignalsTab(accountId: _activeAccountId),
      ReportTab(accountId: _activeAccountId),
      ControlTab(accountId: _activeAccountId),
      AccountsTab(activeAccountId: _activeAccountId, onAccountSelected: setActiveAccount),
    ];

    return Scaffold(
      appBar: AppBar(
        backgroundColor: _bg2,
        elevation: 0,
        title: Row(children: [
          const Text('📈 ', style: TextStyle(fontSize: 18)),
          const Text('TradeBot',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800,
                  color: Color(0xFFe8eaf6))),
        ]),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, color: _txt2, size: 20),
            onPressed: () async {
              await context.read<AuthProvider>().logout();
              if (!mounted) return;
              Navigator.pushReplacementNamed(context, '/login');
            },
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Container(height: 1, color: _border),
        ),
      ),
      body: IndexedStack(index: _idx, children: tabs),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: _bg2,
          border: Border(top: BorderSide(color: _border)),
        ),
        child: BottomNavigationBar(
          currentIndex: _idx,
          onTap: (i) => setState(() => _idx = i),
          backgroundColor: Colors.transparent,
          elevation: 0,
          type: BottomNavigationBarType.fixed,
          selectedItemColor: _accent,
          unselectedItemColor: _txt2,
          selectedFontSize: 10,
          unselectedFontSize: 10,
          items: const [
            BottomNavigationBarItem(icon: Icon(Icons.home_rounded), label: 'Inicio'),
            BottomNavigationBarItem(icon: Icon(Icons.bolt_rounded), label: 'Señales'),
            BottomNavigationBarItem(icon: Icon(Icons.bar_chart_rounded), label: 'Reporte'),
            BottomNavigationBarItem(icon: Icon(Icons.tune_rounded), label: 'Control'),
            BottomNavigationBarItem(icon: Icon(Icons.link_rounded), label: 'Cuentas'),
          ],
        ),
      ),
    );
  }
}
