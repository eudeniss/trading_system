"""
Sistema de Display usando Textual - Layout Ajustado para Template Original
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, DataTable, Label
from textual.reactive import reactive
from textual.timer import Timer
from textual import events
from textual.binding import Binding
from textual.css.query import NoMatches

from datetime import datetime
from collections import deque
from typing import Dict, Any, Optional, List
import asyncio

from domain.entities.market_data import MarketData
from domain.entities.signal import Signal, SignalLevel, SignalSource


class TradingMonitorApp(App):
    """Aplicação Textual principal - Layout conforme template."""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    /* Header simples no topo */
    #header-container {
        height: 3;
        background: $panel;
        border: solid $primary;
        content-align: center middle;
    }
    
    /* Container principal - layout vertical */
    #main-container {
        layout: vertical;
    }
    
    /* Linha com os 3 painéis lado a lado */
    #panels-row {
        height: 40%;
        layout: horizontal;
        margin: 1;
    }
    
    /* Cada painel individual */
    .panel {
        width: 1fr;
        min-width: 29;  /* largura mínima para caber o título */
        border: solid $primary;
        padding: 1;
        margin: 0 1;
        overflow: hidden;  /* IMPORTANTE: esconde overflow */
    }

    #risk-content {
        overflow: hidden;  /* evita vazamento */
        padding-right: 1;  /* espaço extra à direita */
    }
    
    .panel-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    
    /* Área de sinais embaixo ocupando toda largura */
    #signals-area {
        height: 60%;
        border: solid $success;
        padding: 1;
        margin: 1;
    }
    
    #signals-list {
        height: 1fr;
        overflow-y: auto;
    }
    
    .signal-item {
        margin-bottom: 1;
    }
    
    .dim {
        color: $text-disabled;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("c", "clear_signals", "Limpar Sinais"),
        Binding("r", "refresh", "Atualizar"),
    ]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.signals: deque[Signal] = deque(maxlen=50)
        self.market_context = {
            'cvd_total': {'WDO': 0, 'DOL': 0},
            'momentum': {'WDO': 'NEUTRO', 'DOL': 'NEUTRO'},
            'pressure': {'WDO': 'EQUILIBRADO', 'DOL': 'EQUILIBRADO'},
            'signals_today': 0,
            'risk_status': None
        }
    
    def compose(self) -> ComposeResult:
        """Cria o layout conforme template."""
        yield Header()
        
        # Header customizado simples
        with Container(id="header-container"):
            yield Label("", id="header-info")
        
        # Container principal
        with Container(id="main-container"):
            
            # Linha com os 3 painéis
            with Container(id="panels-row"):
                # Painel Arbitragem
                with Container(classes="panel", id="arbitrage-panel"):
                    yield Label("📊 ARBITRAGEM", classes="panel-title")
                    yield Container(id="arbitrage-content")
                
                # Painel Tape Reading
                with Container(classes="panel", id="tape-panel"):
                    yield Label("📈 TAPE READING", classes="panel-title")
                    yield Container(id="tape-content")
                
                # Painel Risk Management
                with Container(classes="panel", id="risk-panel"):
                    yield Label("🛡️ RISK MANAGEMENT", classes="panel-title")
                    yield Container(id="risk-content")
            
            # Área de sinais embaixo
            with Container(id="signals-area"):
                yield Label("📡 SINAIS ATIVOS", classes="panel-title")
                yield ScrollableContainer(Container(id="signals-list"))
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Quando a aplicação é montada."""
        self.title = "Trading Monitor v7.0"
        self.sub_title = "Sistema sem persistência"
        self.update_header()
    
    def update_header(self):
        """Atualiza o header com informações resumidas."""
        cvd_wdo = self.market_context['cvd_total']['WDO']
        cvd_dol = self.market_context['cvd_total']['DOL']
        risk_level = self.market_context.get('risk_status', {}).get('risk_level', 'LOW') if self.market_context.get('risk_status') else 'LOW'
        
        header_text = (
            f"[bold cyan]Sistema de Trading v7.0[/bold cyan]  •  "
            f"CVD Total: [{'green' if cvd_wdo > 0 else 'red'}]WDO {cvd_wdo:+,}[/] | "
            f"[{'green' if cvd_dol > 0 else 'red'}]DOL {cvd_dol:+,}[/]  •  "
            f"Pressão: {self.market_context['pressure']['WDO']} | {self.market_context['pressure']['DOL']}  •  "
            f"Risco: {risk_level}  •  Sinais: {self.market_context['signals_today']}"
        )
        
        try:
            self.query_one("#header-info").update(header_text)
        except NoMatches:
            pass
    
    def update_display(self, market_data: MarketData, analysis_data: Dict[str, Any]):
        """Atualiza todos os painéis com novos dados."""
        # Atualiza contexto
        self._update_context(analysis_data)
        
        # Atualiza header
        self.update_header()
        
        # Atualiza cada painel
        self._update_arbitrage_panel(analysis_data.get('arbitrage_stats'))
        self._update_tape_panel(analysis_data.get('tape_summaries', {}))
        self._update_risk_panel(analysis_data.get('risk_status'))
    
    def _update_arbitrage_panel(self, arb_stats: Optional[Dict]):
        """Atualiza painel de arbitragem."""
        content = self.query_one("#arbitrage-content")
        content.remove_children()
        
        if arb_stats:
            spread = arb_stats.get('current', 0.0)
            mean = arb_stats.get('mean', 0.0)
            std = arb_stats.get('std', 0.0)
            z_score = (spread - mean) / std if std > 0 else 0
            profit_reais = spread * 10
            
            color = "green" if profit_reais > 15 else "yellow" if profit_reais > 0 else "red"
            
            content.mount(Label(f"[{color}]Spread: {spread:.2f} pts (R$ {profit_reais:.0f})[/{color}]"))
            
            z_color = "red" if abs(z_score) > 2 else "yellow" if abs(z_score) > 1 else "white"
            content.mount(Label(f"[{z_color}]Z-Score: {z_score:+.2f}[/{z_color}]"))
            
            bar = self._create_z_score_bar(z_score)
            content.mount(Label(f"[dim]{bar}[/dim]"))
            
            content.mount(Label(""))
            content.mount(Label(f"[dim]Média: {mean:.2f} pts[/dim]"))
            content.mount(Label(f"[dim]Desvio: {std:.2f}[/dim]"))
            content.mount(Label(f"[dim]Min/Max: {arb_stats.get('min', 0):.1f}/{arb_stats.get('max', 0):.1f}[/dim]"))
        else:
            content.mount(Label("[dim]Aguardando dados...[/dim]"))
    
    def _update_tape_panel(self, tape_summaries: Dict):
        """Atualiza painel de tape reading."""
        content = self.query_one("#tape-content")
        content.remove_children()
        
        for symbol in ['WDO', 'DOL']:
            summary = tape_summaries.get(symbol, {})
            if summary:
                content.mount(Label(f"[bold white]{symbol}:[/bold white]"))
                
                cvd = summary.get('cvd', 0)
                cvd_roc = summary.get('cvd_roc', 0)
                cvd_total = summary.get('cvd_total', 0)
                
                cvd_color = "green" if cvd > 0 else "red" if cvd < 0 else "white"
                roc_color = "yellow" if abs(cvd_roc) > 50 else "dim white"
                
                content.mount(Label(f"  [{cvd_color}]CVD: {cvd:+d} (Total: {cvd_total:+,})[/{cvd_color}]"))
                content.mount(Label(f"  [{roc_color}]ROC: {cvd_roc:+.0f}%[/{roc_color}]"))
                
                poc = summary.get('poc')
                if poc:
                    content.mount(Label(f"  [cyan]POC: {poc:.2f}[/cyan]"))
                
                content.mount(Label(""))
    
    def _update_risk_panel(self, risk_status: Optional[Dict]):
        """Atualiza painel de risco."""
        content = self.query_one("#risk-content")
        content.remove_children()
        
        if not risk_status:
            content.mount(Label("[dim]Sistema inicializando...[/dim]"))
            return
        
        risk_level = risk_status.get('risk_level', 'LOW')
        risk_indicators = {
            'LOW': {'color': 'green', 'emoji': '🟢', 'desc': 'Risco Baixo'},
            'MEDIUM': {'color': 'yellow', 'emoji': '🟡', 'desc': 'Risco Médio'},
            'HIGH': {'color': 'orange1', 'emoji': '🟠', 'desc': 'Risco Alto'},
            'CRITICAL': {'color': 'red', 'emoji': '🔴', 'desc': 'Risco Crítico!'}
        }
        
        indicator = risk_indicators.get(risk_level, risk_indicators['LOW'])
        content.mount(Label(f"[bold {indicator['color']}]{indicator['emoji']} {indicator['desc']}[/bold {indicator['color']}]"))
        
        risk_bar = self._create_risk_bar(risk_level)
        content.mount(Label(f"[dim]{risk_bar}[/dim]"))
        
        metrics = risk_status.get('metrics', {})
        if metrics:
            content.mount(Label(""))
            content.mount(Label("[bold white]📊 Métricas:[/bold white]"))
            content.mount(Label(f"  ✓ Aprovação: {metrics.get('approval_rate', '0%')}"))
            content.mount(Label(f"  ⚡ Perdas: {metrics.get('consecutive_losses', 0)}"))
            content.mount(Label(f"  💰 PnL: {metrics.get('daily_pnl', 'R$0.00')}"))
            content.mount(Label(f"  📉 DD: {metrics.get('current_drawdown', '0.0%')}"))
    
    def add_signal(self, signal: Signal):
        """Adiciona um novo sinal."""
        self.signals.appendleft(signal)
        self.market_context['signals_today'] += 1
        self._refresh_signals()
        self.update_header()
    
    def _refresh_signals(self):
        """Atualiza a lista de sinais."""
        container = self.query_one("#signals-list")
        container.remove_children()
        
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
        
        for signal in list(self.signals)[:30]:  # Mostra últimos 30
            level_color = color_map.get(signal.level, 'white')
            emoji = source_emoji.get(signal.source, '📌')
            
            signal_text = (
                f"[cyan]{signal.timestamp.strftime('%H:%M:%S')}[/cyan] "
                f"{emoji} [{level_color}]{signal.message}[/{level_color}]"
            )
            
            container.mount(Label(signal_text, classes="signal-item"))
    
    def _update_context(self, context_data: Dict[str, Any]):
        """Atualiza o contexto de mercado."""
        if 'tape_summaries' in context_data:
            for symbol in ['WDO', 'DOL']:
                summary = context_data['tape_summaries'].get(symbol, {})
                self.market_context['cvd_total'][symbol] = summary.get('cvd_total', 0)
                self.market_context['momentum'][symbol] = self._determine_momentum(summary)
                self.market_context['pressure'][symbol] = self._determine_pressure(summary)
        
        if 'risk_status' in context_data:
            self.market_context['risk_status'] = context_data.get('risk_status')
    
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
    
    def _create_z_score_bar(self, z_score: float) -> str:
        """Cria uma barra visual para o Z-Score."""
        bar_length = 20
        center = bar_length // 2
        z_clamped = max(-3.0, min(3.0, z_score))
        position = int(center + (z_clamped / 3.0) * (center - 1))
        position = max(0, min(bar_length - 1, position))
        
        bar = ['━'] * bar_length
        bar[center] = '┃'
        bar[position] = '█'
        bar[0] = '['
        bar[-1] = ']'
        
        return "".join(bar)
    
    def _create_risk_bar(self, risk_level: str) -> str:
        """Cria uma barra visual do nível de risco."""
        levels = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
        current_index = levels.index(risk_level) if risk_level in levels else 0
        
        bar = []
        for i in range(len(levels)):
            bar.append('█' if i <= current_index else '░')
            if i < len(levels) - 1:
                bar.append(' ')
        
        return f"[{''.join(bar)}]"
    
    def action_clear_signals(self) -> None:
        """Limpa todos os sinais."""
        self.signals.clear()
        self._refresh_signals()
    
    def action_refresh(self) -> None:
        """Força uma atualização."""
        pass


class TextualMonitorDisplay:
    """
    Wrapper para integrar o Textual App com o sistema existente.
    """
    
    def __init__(self, console=None):
        self.app = TradingMonitorApp()
        self.running = False
    
    async def start(self):
        """Inicia a aplicação Textual."""
        self.running = True
        await self.app.run_async()
    
    def stop(self):
        """Para a aplicação."""
        self.running = False
        if self.app.is_running:
            self.app.exit()
    
    def update(self, market_data: MarketData, analysis_data: Dict[str, Any]):
        """Atualiza o display com novos dados."""
        if self.app.is_running:
            self.app.call_from_thread(
                self.app.update_display,
                market_data,
                analysis_data
            )
    
    def add_signal(self, signal: Signal):
        """Adiciona um novo sinal."""
        if self.app.is_running:
            self.app.call_from_thread(self.app.add_signal, signal)
    
    def update_system_phase(self, phase: str):
        """Atualiza a fase do sistema."""
        if self.app.is_running:
            self.app.sub_title = f"Fase: {phase}"