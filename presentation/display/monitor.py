# presentation/display/monitor.py
"""Sistema de Display usando Textual - com renderização otimizada."""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.widgets import Header, Footer, Static, Label
from textual.css.query import NoMatches
from textual.binding import Binding

from datetime import datetime
from collections import deque
from typing import Dict, Any, Optional, List
import logging

from core.entities.market_data import MarketData
from core.entities.signal import Signal, SignalLevel, SignalSource

logger = logging.getLogger(__name__)


class TradingMonitorApp(App):
    """Aplicação Textual principal com renderização otimizada."""
    
    CSS = """
    Screen {
        background: $surface;
    }
    #header-container {
        height: 3;
        background: $panel;
        border: solid $primary;
        content-align: center middle;
    }
    #main-container {
        layout: vertical;
    }
    #panels-row {
        height: 40%;
        margin: 1;
    }
    .panel {
        width: 100%;
        border: solid $primary;
        padding: 1;
        margin: 0 1;
        overflow: hidden;
    }
    /* <<< NOVO: Estilo para as colunas WDO e DOL >>> */
    .column {
        width: 1fr;
    }
    .panel-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    #signals-area {
        height: 1fr;
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
        ("q", "quit", "Sair"),
        ("c", "clear_signals", "Limpar Sinais"),
    ]
    
    def __init__(self, performance_monitor: Any = None, **kwargs):
        super().__init__(**kwargs)
        self.performance_monitor = performance_monitor
        self.signals: deque[Signal] = deque(maxlen=50)
        self.market_context = {
            'cvd_total': {'WDO': 0, 'DOL': 0},
            'pressure': {'WDO': 'NEUTRO', 'DOL': 'NEUTRO'},
            'signals_today': 0,
            'total_trades_processed': 0,
        }
        self.start_time = datetime.now()
    
    # --- MÉTODO COMPOSE CORRIGIDO ---
    def compose(self) -> ComposeResult:
        """Cria o layout da interface, já com a estrutura de colunas."""
        yield Header()
        
        with Container(id="header-container"):
            yield Label("", id="header-info")
        
        with Container(id="main-container"):
            with Container(id="panels-row"):
                with Container(classes="panel", id="tape-panel"):
                    yield Label("📈 TAPE READING & MARKET ANALYSIS", classes="panel-title")
                    # <<< CORREÇÃO AQUI: Cria a estrutura de colunas uma única vez >>>
                    with Horizontal(id="tape-content"):
                        yield Container(id="wdo-col", classes="column")
                        yield Container(id="dol-col", classes="column")
            
            with Container(id="signals-area"):
                yield Label("📡 SINAIS ATIVOS", classes="panel-title", id="signals-title")
                yield ScrollableContainer(Container(id="signals-list"))
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Chamado quando a aplicação é montada."""
        self.title = "Trading Monitor v8.0"
        self.sub_title = "Clean Architecture - Market Calculated"
        self.update_header()
        self.set_interval(1.0, self.update_performance_metrics)
    
    def update_performance_metrics(self):
        """Atualiza as métricas de performance para o display."""
        if self.performance_monitor:
            totals = self.performance_monitor.get_trade_totals()
            self.market_context['total_trades_processed'] = totals.get('total', 0)
        self.update_header()
        
    def update_header(self):
        """Atualiza o header com o total de trades."""
        cvd_wdo = self.market_context['cvd_total']['WDO']
        cvd_dol = self.market_context['cvd_total']['DOL']
        pressure_wdo = self._get_pressure_text(self.market_context['pressure']['WDO'])
        pressure_dol = self._get_pressure_text(self.market_context['pressure']['DOL'])
        total_trades = self.market_context.get('total_trades_processed', 0)
        
        header_text = (
            f"[bold cyan]Sistema de Trading v8.0[/bold cyan]  •  "
            f"CVD: [{'green' if cvd_wdo > 0 else 'red'}]WDO {cvd_wdo:+,}[/] | "
            f"[{'green' if cvd_dol > 0 else 'red'}]DOL {cvd_dol:+,}[/]  •  "
            f"Pressão: WDO {pressure_wdo} | DOL {pressure_dol}  •  "
            f"Sinais: {self.market_context['signals_today']}  •  "
            f"[yellow]Trades Totais: {total_trades:,}[/yellow]"
        )
        try:
            self.query_one("#header-info").update(header_text)
        except NoMatches:
            pass
    
    def _get_pressure_text(self, pressure: str) -> str:
        if "COMPRA" in pressure: return f"[green]COMPRA[/]"
        if "VENDA" in pressure: return f"[red]VENDA[/]"
        return f"[white]NEUTRO[/]"
    
    def update_display(self, market_data: MarketData, analysis_data: Dict[str, Any]):
        """Atualiza todos os painéis com novos dados."""
        self._update_context(analysis_data)
        self.update_header()
        self._update_tape_panel(analysis_data.get('tape_summaries', {}))
    
    # --- MÉTODO DE UPDATE DO PAINEL CORRIGIDO ---
    def _update_tape_panel(self, tape_summaries: Dict):
        """Atualiza o painel de tape reading preenchendo os containers existentes."""
        try:
            # 1. Encontra os containers de coluna que já existem na tela
            wdo_col = self.query_one("#wdo-col")
            dol_col = self.query_one("#dol-col")

            # 2. Limpa o conteúdo antigo de cada coluna
            wdo_col.remove_children()
            dol_col.remove_children()

            # 3. Preenche cada coluna com os novos dados
            summary_wdo = tape_summaries.get('WDO', {})
            self._render_symbol_summary(wdo_col, "WDO", summary_wdo)
            
            summary_dol = tape_summaries.get('DOL', {})
            self._render_symbol_summary(dol_col, "DOL", summary_dol)

        except Exception as e:
            logger.error(f"Erro ao renderizar painel de Tape Reading: {e}")

    def _render_symbol_summary(self, container: Container, symbol: str, summary: Dict):
        """Renderiza o resumo para um único símbolo."""
        if not summary:
            container.mount(Label(f"[bold white]{symbol}:[/bold white] [dim]Aguardando dados...[/dim]"))
            return

        container.mount(Label(f"[bold white]{symbol}:[/bold white]"))
        
        cvd = summary.get('cvd', 0)
        cvd_roc = summary.get('cvd_roc', 0)
        cvd_total = summary.get('cvd_total', 0)
        
        cvd_color = "green" if cvd > 0 else "red" if cvd < 0 else "white"
        roc_color = "yellow" if abs(cvd_roc) > 50 else "dim white"
        
        container.mount(Label(f"  [{cvd_color}]CVD: {cvd:+d} (Total: {cvd_total:+,})[/{cvd_color}]"))
        container.mount(Label(f"  [{roc_color}]ROC: {cvd_roc:+.0f}%[/{roc_color}]"))
        
        poc = summary.get('poc')
        if poc:
            container.mount(Label(f"  [cyan]POC: {poc:.2f}[/cyan]"))
    
    def add_signal(self, signal: Signal):
        self.signals.appendleft(signal)
        self.market_context['signals_today'] += 1
        self._refresh_signals()
        self.update_header()
    
    def _refresh_signals(self):
        """Atualiza a lista de sinais."""
        try:
            container = self.query_one("#signals-list")
            container.remove_children()
            title = self.query_one("#signals-title")
            title.update(f"📡 SINAIS ATIVOS ({len(self.signals)})")
            
            color_map = { SignalLevel.INFO: 'blue', SignalLevel.WARNING: 'yellow', SignalLevel.ALERT: 'red' }
            source_emoji = {
                SignalSource.TAPE_READING: '📊',
                SignalSource.CONFLUENCE: '🔥',
                SignalSource.SYSTEM: '⚙️',
                SignalSource.MANIPULATION: '🚨'
            }
            
            for signal in list(self.signals)[:30]:
                level_color = color_map.get(signal.level, 'white')
                emoji = source_emoji.get(signal.source, '📌')
                signal_text = f"[cyan]{signal.timestamp.strftime('%H:%M:%S')}[/cyan] {emoji} [{level_color}]{signal.message}[/{level_color}]"
                container.mount(Label(signal_text, classes="signal-item"))
        except NoMatches:
            pass
    
    def _update_context(self, context_data: Dict[str, Any]):
        """Atualiza o contexto de mercado."""
        if 'tape_summaries' in context_data:
            for symbol in ['WDO', 'DOL']:
                summary = context_data['tape_summaries'].get(symbol, {})
                self.market_context['cvd_total'][symbol] = summary.get('cvd_total', 0)
                
                cvd = summary.get('cvd', 0)
                if cvd > 50: self.market_context['pressure'][symbol] = 'COMPRA'
                elif cvd < -50: self.market_context['pressure'][symbol] = 'VENDA'
                else: self.market_context['pressure'][symbol] = 'NEUTRO'
    
    def action_clear_signals(self) -> None:
        """Limpa todos os sinais."""
        self.signals.clear()
        self._refresh_signals()


class TextualMonitorDisplay:
    """Wrapper para integrar o Textual App com o sistema existente."""
    
    def __init__(self, console=None, performance_monitor: Any = None):
        self.app = TradingMonitorApp(performance_monitor=performance_monitor)
        self.running = False
    
    async def start(self):
        self.running = True
        await self.app.run_async()
    
    def stop(self):
        self.running = False
        if self.app.is_running:
            try:
                self.app.exit()
            except Exception as e:
                logger.error(f"Erro ao tentar fechar o app Textual: {e}")
    
    def update(self, market_data: MarketData, analysis_data: Dict[str, Any]):
        if self.app.is_running and not getattr(self.app, '_exit', False):
            self.app.call_from_thread(self.app.update_display, market_data, analysis_data)
    
    def add_signal(self, signal: Signal):
        if self.app.is_running and not getattr(self.app, '_exit', False):
            self.app.call_from_thread(self.app.add_signal, signal)
    
    def update_system_phase(self, phase: str):
        if self.app.is_running:
            self.app.sub_title = f"Fase: {phase}"