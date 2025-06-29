from datetime import datetime
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.table import Table
from collections import deque
from typing import Dict, Any, Tuple, Optional

from domain.entities.market_data import MarketData
from domain.entities.signal import Signal, SignalLevel, SignalSource

class MonitorDisplay:
    """
    Classe responsável por renderizar a interface simplificada no console.
    Versão reduzida sem Times & Trades e Books.
    """
    def __init__(self, console: Console):
        self.console = console
        self.layout = self._create_layout()
        self.signals: deque[Signal] = deque(maxlen=20)
        
        # Controle anti-spam
        self.last_system_message = ""
        self.system_message_count = 0
        self.max_system_repeats = 2
        
        self.market_context = {
            'cvd_total': {'WDO': 0, 'DOL': 0},
            'momentum': {'WDO': 'NEUTRO', 'DOL': 'NEUTRO'},
            'pressure': {'WDO': 'EQUILIBRADO', 'DOL': 'EQUILIBRADO'},
            'active_supports': {'WDO': [], 'DOL': []},
            'risk_status': None,
            'market_regime': {'WDO': 'NORMAL', 'DOL': 'NORMAL'}
        }
        
        self.system_status = {
            'phase': 'INITIALIZATION',
            'uptime': 0,
            'signals_today': 0,
            'last_signal': None
        }

    def _create_layout(self) -> Layout:
        """Cria a estrutura simplificada do layout."""
        layout = Layout(name="root")
        
        # Layout principal simplificado
        layout.split(
            Layout(name="header", size=6),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=1),
        )
        
        # Body dividido em seção de análise e sinais
        layout["body"].split(
            Layout(name="analysis_section", size=12),
            Layout(name="signals_panel", ratio=1),
        )
        
        # Seção de análise com 3 painéis
        layout["analysis_section"].split_row(
            Layout(name="arbitrage_panel", ratio=1),
            Layout(name="tape_reading_panel", ratio=1),
            Layout(name="risk_panel", ratio=1)
        )
        
        return layout

    def add_signal(self, signal: Signal):
        """Adiciona um novo sinal à fila de exibição com controle anti-spam."""
        # Anti-spam para mensagens System
        if signal.source == SignalSource.SYSTEM:
            if "Qualidade moderada" in signal.message:
                return
            
            if signal.message == self.last_system_message:
                self.system_message_count += 1
                if self.system_message_count > self.max_system_repeats:
                    return
            else:
                self.last_system_message = signal.message
                self.system_message_count = 1
        
        self.signals.appendleft(signal)
        self.system_status['signals_today'] += 1
        self.system_status['last_signal'] = datetime.now()

    def update_context(self, context_data: Dict[str, Any]):
        """Atualiza o contexto de mercado para exibição no header."""
        if 'tape_summaries' in context_data:
            for symbol in ['WDO', 'DOL']:
                summary = context_data['tape_summaries'].get(symbol, {})
                self.market_context['cvd_total'][symbol] = summary.get('cvd_total', 0)
                self.market_context['momentum'][symbol] = self._determine_momentum(summary)
                self.market_context['pressure'][symbol] = self._determine_pressure(summary)
                self.market_context['active_supports'][symbol] = summary.get('supports', [])
        
        if 'risk_status' in context_data:
            self.market_context['risk_status'] = context_data.get('risk_status')
        
        if 'market_context' in context_data:
            regime_info = context_data['market_context'].get('regime', 'NORMAL')
            self.market_context['market_regime'] = {'WDO': regime_info, 'DOL': regime_info}

    def _determine_momentum(self, summary: Dict) -> str:
        """Determina o momentum baseado no CVD ROC."""
        cvd_roc = summary.get('cvd_roc', 0)
        if cvd_roc > 50: return "ALTA 📈"
        if cvd_roc < -50: return "BAIXA 📉"
        return "NEUTRO ➡️"
    
    def _determine_pressure(self, summary: Dict) -> str:
        """Determina a pressão dominante."""
        cvd = summary.get('cvd', 0)
        if cvd > 100: return "COMPRA FORTE 🟢"
        if cvd < -100: return "VENDA FORTE 🔴"
        if cvd > 50: return "COMPRA 🟢"
        if cvd < -50: return "VENDA 🔴"
        return "EQUILIBRADO ⚖️"

    def update(self, market_data: MarketData, analysis_data: Dict[str, Any]) -> Panel:
        """Atualiza todos os painéis no layout simplificado."""
        self.update_context(analysis_data)
        
        # Cria os painéis de análise
        arbitrage_panel = self._create_arbitrage_panel(analysis_data)
        tape_reading_panel = self._create_tape_reading_panel(analysis_data)
        risk_panel = self._create_risk_panel(analysis_data)
        
        self.layout["arbitrage_panel"].update(arbitrage_panel)
        self.layout["tape_reading_panel"].update(tape_reading_panel)
        self.layout["risk_panel"].update(risk_panel)
        
        # Filtra e atualiza sinais
        filtered_signals = self._filter_signals_for_display()
        self.layout["signals_panel"].update(self._create_signals_panel(filtered_signals))

        # Atualiza header e footer
        self._update_header_with_context()
        
        footer_text = Text(f"[ {self.system_status['phase']} ] Pressione Ctrl+C para Sair", justify="center", style="dim yellow")
        self.layout["footer"].update(Align.center(footer_text))
        
        return Panel(self.layout, border_style="dim")
    
    def _filter_signals_for_display(self) -> list:
        """Filtra sinais para evitar spam no display."""
        filtered = []
        seen_system_messages = set()
        
        for signal in self.signals:
            if signal.source in [SignalSource.TAPE_READING, SignalSource.ARBITRAGE, 
                                SignalSource.CONFLUENCE, SignalSource.MANIPULATION]:
                filtered.append(signal)
            elif signal.source == SignalSource.SYSTEM:
                if signal.message not in seen_system_messages:
                    seen_system_messages.add(signal.message)
                    filtered.append(signal)
            
            if len(filtered) >= 15:
                break
        
        return filtered
    
    def _update_header_with_context(self):
        """Atualiza o header com informações consolidadas de mercado."""
        title_line = Text(f"Sistema de Trading v7.0 - {datetime.now():%H:%M:%S}", justify="center", style="bold cyan")
        
        # CVD e Momentum
        cvd_wdo = self.market_context['cvd_total']['WDO']
        cvd_dol = self.market_context['cvd_total']['DOL']
        
        main_line = Text(justify="center")
        main_line.append("CVD Total: ", style="dim white")
        main_line.append(f"WDO {cvd_wdo:+,} ", style="green" if cvd_wdo > 0 else "red")
        main_line.append("| ", style="dim white")
        main_line.append(f"DOL {cvd_dol:+,}", style="green" if cvd_dol > 0 else "red")
        main_line.append("  •  ", style="dim white")
        main_line.append("Momentum: ", style="dim white")
        main_line.append(f"{self.market_context['momentum']['WDO']} | {self.market_context['momentum']['DOL']}", style="yellow")
        
        # Pressão e Regime
        pressure_line = Text(justify="center")
        pressure_line.append("Pressão: ", style="dim white")
        pressure_line.append(f"WDO {self.market_context['pressure']['WDO']} | DOL {self.market_context['pressure']['DOL']}", style="cyan")
        
        # Risk e Status
        status_line = Text(justify="center")
        
        # Escoras ativas
        wdo_supports = len(self.market_context['active_supports']['WDO'])
        dol_supports = len(self.market_context['active_supports']['DOL'])
        if wdo_supports > 0 or dol_supports > 0:
            status_line.append(f"🛡️ Escoras: WDO {wdo_supports} | DOL {dol_supports}", style="cyan")
            status_line.append("  •  ", style="dim white")
        
        # Risk Level
        if self.market_context.get('risk_status'):
            risk = self.market_context['risk_status']
            risk_level = risk.get('risk_level', 'LOW')
            risk_color = {'LOW': 'green', 'MEDIUM': 'yellow', 'HIGH': 'orange1', 'CRITICAL': 'red'}.get(risk_level, 'white')
            status_line.append(f"Risco: {risk_level}", style=risk_color)
            if risk.get('active_breakers'):
                status_line.append(" ⚠️", style="red blink")
            status_line.append("  •  ", style="dim white")
        
        # Sinais hoje
        status_line.append(f"Sinais: {self.system_status['signals_today']}", style="dim white")
        
        header_content = Text.assemble(title_line, "\n", main_line, "\n", pressure_line, "\n", status_line)
        self.layout["header"].update(Panel(Align.center(header_content, vertical="middle"), border_style="cyan", title="[bold]Market Overview[/bold]"))
    
    def _create_arbitrage_panel(self, analysis_data: Dict[str, Any]) -> Panel:
        """Cria painel de arbitragem com mais detalhes."""
        content = []
        arb_stats = analysis_data.get('arbitrage_stats')
        
        if arb_stats:
            spread = arb_stats.get('current', 0.0)
            mean = arb_stats.get('mean', 0)
            std = arb_stats.get('std', 0)
            z_score = (spread - mean) / std if std > 0 else 0
            
            # Spread e valor em reais
            profit_reais = spread * 10  # Point value
            color = "green" if profit_reais > 15 else "yellow" if profit_reais > 0 else "red"
            
            content.append(Text(f"Spread: {spread:.2f} pts (R$ {profit_reais:.0f})", style=f"bold {color}"))
            
            # Z-Score com barra visual
            z_bar = self._create_z_score_bar(z_score)
            z_color = "red" if abs(z_score) > 2 else "yellow" if abs(z_score) > 1 else "white"
            content.append(Text(f"Z-Score: {z_score:+.2f}", style=z_color))
            content.append(Text(z_bar, style="dim"))
            
            # Estatísticas
            content.append(Text(""))
            content.append(Text(f"Média: {mean:.2f} pts", style="dim"))
            content.append(Text(f"Desvio: {std:.2f}", style="dim"))
            content.append(Text(f"Min/Max: {arb_stats.get('min', 0):.1f}/{arb_stats.get('max', 0):.1f}", style="dim"))
        else:
            content.append(Text("Aguardando dados...", style="dim"))
        
        return Panel(Text("\n").join(content), title="📊 Arbitragem", border_style="magenta")

    def _create_tape_reading_panel(self, analysis_data: Dict[str, Any]) -> Panel:
        """Cria painel de tape reading com informações detalhadas."""
        content = []
        
        for symbol in ['WDO', 'DOL']:
            summary = analysis_data.get('tape_summaries', {}).get(symbol, {})
            if summary:
                # Título do símbolo
                content.append(Text(f"{symbol}:", style="bold white"))
                
                # CVD e ROC
                cvd = summary.get('cvd', 0)
                cvd_roc = summary.get('cvd_roc', 0)
                cvd_total = summary.get('cvd_total', 0)
                
                cvd_color = "green" if cvd > 0 else "red" if cvd < 0 else "white"
                roc_color = "yellow" if abs(cvd_roc) > 50 else "dim white"
                
                content.append(Text(f"  CVD: {cvd:+d} (Total: {cvd_total:+,})", style=cvd_color))
                content.append(Text(f"  ROC: {cvd_roc:+.0f}%", style=roc_color))
                
                # POC se disponível
                poc = summary.get('poc')
                if poc:
                    content.append(Text(f"  POC: {poc:.2f}", style="cyan"))
                
                content.append(Text(""))  # Espaço entre símbolos
        
        if not content:
            content.append(Text("Analisando fluxo...", style="dim"))
        else:
            # Remove o último espaço em branco
            content = content[:-1]
        
        return Panel(Text("\n").join(content), title="📈 Tape Reading", border_style="blue")
    
# presentation/display/monitor_display.py
# SUBSTITUA APENAS A FUNÇÃO _create_risk_panel PELA VERSÃO ABAIXO:

    def _create_risk_panel(self, analysis_data: Dict[str, Any]) -> Panel:
        """Cria painel de gerenciamento de risco com indicadores visuais claros."""
        content = []
        risk_status = analysis_data.get('risk_status')
        
        if risk_status:
            # Risk Level com indicador visual e explicação
            risk_level = risk_status.get('risk_level', 'LOW')
            risk_indicators = {
                'LOW': {
                    'color': 'green',
                    'emoji': '🟢',
                    'desc': 'Risco Baixo - Operação Normal'
                },
                'MEDIUM': {
                    'color': 'yellow', 
                    'emoji': '🟡',
                    'desc': 'Risco Médio - Atenção Redobrada'
                },
                'HIGH': {
                    'color': 'orange1',
                    'emoji': '🟠', 
                    'desc': 'Risco Alto - Reduzir Exposição'
                },
                'CRITICAL': {
                    'color': 'red',
                    'emoji': '🔴',
                    'desc': 'Risco Crítico - Parar Operações!'
                }
            }
            
            indicator = risk_indicators.get(risk_level, risk_indicators['LOW'])
            content.append(Text(f"{indicator['emoji']} {indicator['desc']}", style=f"bold {indicator['color']}"))
            
            # Barra visual de risco
            risk_bar = self._create_risk_bar(risk_level)
            content.append(Text(risk_bar, style="dim"))
            
            # Métricas
            metrics = risk_status.get('metrics', {})
            if metrics:
                content.append(Text(""))
                content.append(Text("📊 Métricas:", style="bold white"))
                
                # Taxa de aprovação com cor
                approval_rate = metrics.get('approval_rate', '0%')
                approval_value = float(approval_rate.replace('%', ''))
                approval_color = "green" if approval_value > 70 else "yellow" if approval_value > 50 else "red"
                content.append(Text(f"  ✓ Aprovação: {approval_rate}", style=approval_color))
                
                # Perdas consecutivas
                losses = metrics.get('consecutive_losses', 0)
                losses_color = "white" if losses < 3 else "yellow" if losses < 5 else "red"
                content.append(Text(f"  ⚡ Perdas Consec.: {losses}", style=losses_color))
                
                # PnL com cor
                pnl_str = metrics.get('daily_pnl', 'R$0.00')
                pnl_value = float(pnl_str.replace('R$', '').replace(',', '.'))
                pnl_color = "green" if pnl_value > 0 else "red" if pnl_value < 0 else "white"
                content.append(Text(f"  💰 PnL Diário: {pnl_str}", style=pnl_color))
                
                # Drawdown
                dd_str = metrics.get('current_drawdown', '0.0%')
                dd_value = float(dd_str.replace('%', ''))
                dd_color = "white" if dd_value < 1 else "yellow" if dd_value < 2 else "red"
                content.append(Text(f"  📉 Drawdown: {dd_str}", style=dd_color))
            
            # Circuit Breakers com explicação
            active_breakers = risk_status.get('active_breakers', [])
            if active_breakers:
                content.append(Text(""))
                content.append(Text("⚠️ Circuit Breakers Ativos:", style="red bold blink"))
                
                breaker_explanations = {
                    'frequency': '🚦 Muitos sinais em pouco tempo',
                    'quality': '📊 Qualidade dos sinais baixa',
                    'drawdown': '📉 Perda máxima atingida',
                    'consecutive_losses': '❌ Sequência de perdas',
                    'emergency': '🚨 Stop loss de emergência'
                }
                
                for breaker in active_breakers[:3]:
                    explanation = breaker_explanations.get(breaker, breaker)
                    content.append(Text(f"  {explanation}", style="red"))
        else:
            content.append(Text("Sistema inicializando...", style="dim"))
            content.append(Text(""))
            content.append(Text("Legenda dos Indicadores:", style="bold white"))
            content.append(Text("🟢 Risco Baixo - Tudo OK", style="green"))
            content.append(Text("🟡 Risco Médio - Cautela", style="yellow"))
            content.append(Text("🟠 Risco Alto - Cuidado!", style="orange1"))
            content.append(Text("🔴 Risco Crítico - PARE!", style="red"))
        
        return Panel(Text("\n").join(content), title="🛡️ Risk Management", border_style="orange1")

    def _create_risk_bar(self, risk_level: str) -> str:
        """Cria uma barra visual do nível de risco."""
        levels = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
        current_index = levels.index(risk_level) if risk_level in levels else 0
        
        bar = []
        for i, level in enumerate(levels):
            if i <= current_index:
                bar.append('█')
            else:
                bar.append('░')
            if i < len(levels) - 1:
                bar.append(' ')
        
        return f"[{''.join(bar)}]"

# ADICIONE TAMBÉM ESTA FUNÇÃO NO FINAL DA CLASSE MonitorDisplay SE NÃO EXISTIR
    
    def _create_signals_panel(self, signals: list) -> Panel:
        """Cria painel de sinais em formato compacto."""
        table = Table(
            title="📡 SINAIS ATIVOS",
            show_header=True,
            header_style="bold white",
            title_style="bold yellow",
            box=None,
            padding=(0, 1)
        )
        
        table.add_column("Hora", style="cyan", width=8)
        table.add_column("Tipo", width=10)
        table.add_column("Sinal", no_wrap=False)  # Permite quebra de linha
        
        color_map = {
            SignalLevel.INFO: 'blue',
            SignalLevel.WARNING: 'yellow',
            SignalLevel.ALERT: 'red'
        }
        
        source_emoji = {
            SignalSource.ARBITRAGE: '💹',
            SignalSource.TAPE_READING: '📊',
            SignalSource.CONFLUENCE: '🔥',
            SignalSource.SYSTEM: '⚙️',
            SignalSource.MANIPULATION: '🚨'
        }
        
        for signal in signals:
            level_color = color_map.get(signal.level, 'white')
            emoji = source_emoji.get(signal.source, '📌')
            source_short = signal.source.name[:8]  # Primeiros 8 caracteres
            
            table.add_row(
                signal.timestamp.strftime('%H:%M:%S'),
                f"{emoji} {source_short}",
                f"[{level_color}]{signal.message}[/{level_color}]"
            )
        
        return Panel(table, border_style="green")
    
    def _create_z_score_bar(self, z_score: float) -> str:
        """Cria uma barra visual para o Z-Score."""
        bar_length = 20
        center = bar_length // 2
        
        z_clamped = max(-3.0, min(3.0, z_score))
        position_float = center + (z_clamped / 3.0) * (center - 1)
        position = int(round(position_float))
        position = max(0, min(bar_length - 1, position))
        
        bar = ['─'] * bar_length
        bar[center] = '│'
        bar[position] = '█'
        bar[0] = '['
        bar[-1] = ']'
        
        return "".join(bar)
    
    def update_system_phase(self, phase: str):
        """Atualiza a fase operacional do sistema."""
        self.system_status['phase'] = phase