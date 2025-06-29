# presentation/display/components/signal_panel.py
from typing import List
from rich.table import Table
from rich.panel import Panel
from domain.entities.signal import Signal, SignalLevel, SignalSource

def create_signals_panel(signals: List[Signal]) -> Panel:
    """Cria um painel Rich para exibir os sinais ativos."""
    table = Table(
        title="📊 SINAIS ATIVOS",
        show_header=True,
        header_style="bold white",
        title_style="bold yellow",
        box=None,
        padding=(0, 1)
    )
    table.add_column("Hora", style="cyan", width=9)
    table.add_column("Fonte", width=12)
    table.add_column("Sinal", no_wrap=True, width=60)

    color_map = {
        SignalLevel.INFO: 'blue',
        SignalLevel.WARNING: 'yellow',
        SignalLevel.ALERT: 'red'
    }

    for signal in signals:
        level_color = color_map.get(signal.level, 'white')
        source_name = signal.source.name.replace('_', ' ').title()

        table.add_row(
            signal.timestamp.strftime('%H:%M:%S'),
            f"[{level_color}]{source_name}[/{level_color}]",
            f"[{level_color}]{signal.message}[/{level_color}]"
        )
        
    return Panel(table, border_style="red")