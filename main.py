# main.py
"""
Trading System v8.0 - Com Backtesting via Argumento de Data
Agora aceita data no formato DDMMYYYY para replay de mercado
"""
import sys
import logging
import signal
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.logging import RichHandler

from core.bootstrap.system import SystemBootstrap


def setup_logging(console: Console) -> None:
    """Configura o sistema de logging."""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    
    file_handler = logging.FileHandler(
        log_dir / "system.log", 
        mode='w', 
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    
    console_handler = RichHandler(
        console=console,
        level=logging.INFO,
        show_time=False,
        markup=True
    )
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def print_banner(console: Console, target_date: datetime = None) -> None:
    """Exibe o banner do sistema, indicando se está em modo de replay."""
    mode = f"[bold yellow]REPLAY DE MERCADO: {target_date.strftime('%d/%m/%Y')}[/bold yellow]" if target_date else "[bold green]MERCADO AO VIVO[/bold green]"
    
    banner = f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║      TRADING SYSTEM v8.0 - MERCADO CALCULADO              ║
    ║      {mode.center(53)}      ║
    ║                                                           ║
    ║  🚀 Integração Frajola + Tape Reading                     ║
    ║  📊 Sinais de Alta Confluência ($)                        ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


def verify_environment(console: Console) -> bool:
    """Verifica o ambiente antes de iniciar."""
    try:
        if sys.version_info < (3, 8):
            console.print("[red]❌ Python 3.8+ necessário[/red]")
            return False
        
        config_path = Path('config/config.yaml')
        if not config_path.exists():
            console.print(f"[red]❌ Arquivo de configuração não encontrado: {config_path}[/red]")
            return False
        
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        excel_file = config.get('excel', {}).get('file', '')
        if excel_file and not Path(excel_file).exists():
            console.print(f"[yellow]⚠️ Arquivo Excel não encontrado: {excel_file}[/yellow]")
            console.print("[yellow]O sistema tentará conectar a uma instância já aberta[/yellow]")
        
        console.print("[green]✓ Ambiente verificado[/green]")
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Erro ao verificar ambiente: {e}[/red]")
        return False


def show_calculated_levels(console: Console, bootstrap) -> None:
    """Exibe os níveis calculados do dia."""
    try:
        if 'calculated_market' in bootstrap.services:
            calc_market = bootstrap.services['calculated_market']
            levels = calc_market.get_current_levels()
            fair_value = calc_market.get_fair_value()
            
            console.print("\n[bold cyan]📊 NÍVEIS CALCULADOS DO DIA:[/bold cyan]")
            console.print(f"[yellow]Valor Justo (BASE): {fair_value:.2f}[/yellow]\n")
            
            # Ordena por preço (maior para menor)
            sorted_levels = sorted(levels.items(), key=lambda x: x[1].price, reverse=True)
            
            for name, level in sorted_levels:
                color = "red" if level.type == "RESISTENCIA" else "green" if level.type == "SUPORTE" else "yellow"
                console.print(f"  {name:12} {level.price:>8.2f} [{color}]{level.type}[/{color}]")
    except Exception as e:
        console.print(f"[yellow]⚠️ Não foi possível exibir níveis: {e}[/yellow]")


def main() -> None:
    """Função principal que aceita uma data como argumento para backtest."""
    console = Console()
    
    # --- LÓGICA DE BACKTESTING COM FORMATO DDMMYYYY ---
    target_date = None
    if len(sys.argv) > 1:
        try:
            date_str = sys.argv[1]
            # Aceita formato DDMMYYYY (ex: 07072025)
            target_date = datetime.strptime(date_str, '%d%m%Y')
            console.print(f"[yellow]🔄 Modo REPLAY ativado para: {target_date.strftime('%d/%m/%Y')}[/yellow]")
        except ValueError:
            console.print(f"[red]❌ Formato de data inválido. Use DDMMYYYY (ex: 07072025).[/red]")
            return
    # --- FIM DA LÓGICA DE BACKTESTING ---
    
    print_banner(console, target_date)
    setup_logging(console)
    
    if not verify_environment(console):
        console.print("\n[yellow]Verifique os requisitos e tente novamente.[/yellow]")
        return
    
    console.print("\n[cyan]Inicializando sistema...[/cyan]")
    
    # Passa a data do replay (ou None se for ao vivo) para o Bootstrap
    bootstrap = SystemBootstrap(target_date=target_date)
    
    if not bootstrap.initialize():
        console.print("\n[red]❌ Falha na inicialização do sistema[/red]")
        return
    
    # Mostra os níveis calculados para a data correta
    show_calculated_levels(console, bootstrap)
    
    def signal_handler(sig, frame):
        console.print("\n[yellow]⏹️  Sinal de interrupção recebido[/yellow]")
        bootstrap.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    console.print("\n[green]✅ Sistema iniciado com sucesso![/green]")
    console.print("[cyan]Pressione Ctrl+C para encerrar[/cyan]\n")
    
    try:
        bootstrap.run()
    except Exception as e:
        logging.critical(f"Erro fatal: {e}", exc_info=True)
        console.print(f"\n[red]💥 Erro fatal: {e}[/red]")
    finally:
        bootstrap.shutdown()


if __name__ == "__main__":
    main()