# presentation/display/components/trade_panel.py
from typing import List
from rich.table import Table
from rich.panel import Panel
from domain.entities.trade import Trade, TradeSide

def create_trades_panel(title: str, trades: List[Trade]) -> Panel:
    """Cria um painel Rich para exibir uma lista de trades."""
    table = Table(show_header=True, header_style="bold white", box=None, padding=(0, 1))
    table.add_column("Hora", style="cyan", width=10)
    table.add_column("Agressor", width=10)
    table.add_column("Valor", justify="right", style="white", width=10)
    table.add_column("Qtde", justify="right", width=6)

    for trade in trades:
        side_text = "Comprador" if trade.side == TradeSide.BUY else "Vendedor"
        side_color = "green" if trade.side == TradeSide.BUY else "red"
        
        table.add_row(
            trade.time_str[:10], # Exibe a string de tempo original
            f"[{side_color}]{side_text}[/{side_color}]",
            f"{trade.price:.2f}",
            str(trade.volume)
        )
    
    return Panel(table, title=title, border_style="green")