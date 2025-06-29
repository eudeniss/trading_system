# presentation/display/components/book_panel.py
from typing import List
from rich.table import Table
from rich.panel import Panel
from domain.entities.book import OrderBook
from config import settings

def create_book_panel(title: str, book: OrderBook) -> Panel:
    """Cria um painel Rich para exibir o livro de ofertas."""
    book_levels = settings.DISPLAY_CONFIG.get('book_levels', 5)
    
    table = Table(show_header=True, header_style="bold white", box=None, padding=(0, 1))
    table.add_column("Qtde C", justify="right", width=8, style="dim")
    table.add_column("Compra", justify="right", style="green", width=10)
    table.add_column("Venda", justify="right", style="red", width=10)
    table.add_column("Qtde V", justify="right", width=8, style="dim")

    bids = book.bids[:book_levels]
    asks = book.asks[:book_levels]
    max_len = max(len(bids), len(asks))

    for i in range(max_len):
        bid_vol = str(bids[i].volume) if i < len(bids) else ""
        bid_price = f"{bids[i].price:.2f}" if i < len(bids) else ""
        ask_price = f"{asks[i].price:.2f}" if i < len(asks) else ""
        ask_vol = str(asks[i].volume) if i < len(asks) else ""
        
        table.add_row(bid_vol, bid_price, ask_price, ask_vol)
        
    return Panel(table, title=title, border_style="yellow")