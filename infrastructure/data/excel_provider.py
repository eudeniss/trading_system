#infrastructure/data/excel_provider.py
"""Provider de dados do Excel - FASE 3.1 COM TIMESTAMPS REAIS."""
import xlwings as xw
from datetime import datetime, time as dt_time
import logging
from typing import Any, Optional, List, Dict, Union
from pathlib import Path

from core.entities.trade import Trade, TradeSide
from core.entities.book import OrderBook, BookLevel
from core.entities.market_data import MarketData, MarketSymbolData
from core.contracts.providers import IMarketDataProvider

logger = logging.getLogger(__name__)


class ExcelMarketProvider(IMarketDataProvider):
    """
    Implementação de IMarketDataProvider que lê dados de um arquivo Excel.
    FASE 3.1: Implementa parsing de timestamps reais dos trades
    """
    
    __slots__ = ['file_path', 'sheet_name', 'wb', 'sheet', 'connected', 'config', '_timestamp_cache']
    
    def __init__(self, file_path: str, sheet_name: str, config: Dict = None):
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.wb: Optional[xw.Book] = None
        self.sheet: Optional[xw.Sheet] = None
        self.connected = False
        
        # Cache para timestamps parseados
        self._timestamp_cache: Dict[str, datetime] = {}
        
        # Se config for passado, usa ele. Senão, usa configuração padrão
        if config:
            self.config = self._build_config_from_yaml(config)
        else:
            # Configuração padrão para compatibilidade
            self.config = {
                'WDO': {
                    'trades': {
                        'range': 'B4:E103',
                        'columns': {'time': 0, 'side': 1, 'price': 2, 'volume': 3}
                    },
                    'book': {
                        'bid_range': 'N4:Q13',
                        'ask_range': 'R4:U13'
                    }
                },
                'DOL': {
                    'trades': {
                        'range': 'H4:K103',
                        'columns': {'time': 0, 'side': 1, 'price': 2, 'volume': 3}
                    },
                    'book': {
                        'bid_range': 'X4:AA13',
                        'ask_range': 'AB4:AE13'
                    }
                }
            }
        
        logger.info(f"ExcelMarketProvider configurado - WDO: {self.config['WDO']['trades']['range']}, DOL: {self.config['DOL']['trades']['range']}")

    def _build_config_from_yaml(self, yaml_config: Dict) -> Dict:
        """Constrói configuração interna a partir do config.yaml."""
        return {
            'WDO': {
                'trades': {
                    'range': yaml_config.get('wdo', {}).get('trades', {}).get('range', 'B4:E103'),
                    'columns': yaml_config.get('wdo', {}).get('trades', {}).get('columns', {
                        'time': 0, 'side': 1, 'price': 2, 'volume': 3
                    })
                },
                'book': {
                    'bid_range': yaml_config.get('wdo', {}).get('book', {}).get('bid_range', 'N4:Q13'),
                    'ask_range': yaml_config.get('wdo', {}).get('book', {}).get('ask_range', 'R4:U13')
                }
            },
            'DOL': {
                'trades': {
                    'range': yaml_config.get('dol', {}).get('trades', {}).get('range', 'H4:K103'),
                    'columns': yaml_config.get('dol', {}).get('trades', {}).get('columns', {
                        'time': 0, 'side': 1, 'price': 2, 'volume': 3
                    })
                },
                'book': {
                    'bid_range': yaml_config.get('dol', {}).get('book', {}).get('bid_range', 'X4:AA13'),
                    'ask_range': yaml_config.get('dol', {}).get('book', {}).get('ask_range', 'AB4:AE13')
                }
            }
        }

    def connect(self) -> bool:
        """Conecta ao arquivo Excel."""
        try:
            file_name = Path(self.file_path).name
            try:
                # Tenta conectar a uma instância já aberta
                self.wb = xw.Book(file_name)
                logger.info(f"Conectado à instância EXISTENTE de '{file_name}'")
            except Exception:
                # Se falhar, tenta abrir o arquivo
                logger.warning(f"Não foi possível conectar a uma instância aberta de '{file_name}'. Tentando abrir...")
                self.wb = xw.Book(self.file_path)
                logger.info(f"Arquivo '{self.file_path}' aberto com sucesso.")
            
            self.sheet = self.wb.sheets[self.sheet_name]
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Falha ao conectar ao Excel: {e}", exc_info=True)
            return False

    def get_market_data(self) -> Optional[MarketData]:
        """Retorna um snapshot completo dos dados de mercado."""
        if not self.connected:
            logger.warning("Provider não está conectado")
            return None
            
        timestamp = datetime.now()
        market_data_map: Dict[str, MarketSymbolData] = {}
        
        for symbol in ['WDO', 'DOL']:
            trades = self._read_trades(symbol)
            book = self._read_book(symbol)
            
            # Calcula last_price e total_volume
            if trades:
                last_price = trades[-1].price
                total_volume = sum(t.volume for t in trades)
            else:
                last_price = self._calculate_mid_price(book)
                total_volume = 0
            
            market_data_map[symbol] = MarketSymbolData(
                trades=trades,
                book=book,
                last_price=last_price,
                total_volume=total_volume
            )
        
        return MarketData(timestamp=timestamp, data=market_data_map)

    def _parse_time(self, time_value: Union[str, dt_time, float], now_date: datetime, row_index: int) -> datetime:
        """
        FASE 3.1: Converte valor de tempo do Excel em datetime real.
        
        Args:
            time_value: Valor de tempo vindo do Excel (pode ser string, time ou float)
            now_date: Data atual para combinar com o horário
            row_index: Índice da linha para cache e fallback
            
        Returns:
            datetime com timestamp preciso
        """
        # Tenta cache primeiro
        cache_key = f"{time_value}_{now_date.date()}"
        if cache_key in self._timestamp_cache:
            return self._timestamp_cache[cache_key]
        
        result = None
        
        try:
            # Se já é um objeto time do Excel
            if isinstance(time_value, dt_time):
                result = datetime.combine(now_date.date(), time_value)
            
            # Se é um float (Excel armazena tempo como fração do dia)
            elif isinstance(time_value, (int, float)):
                # Excel: 0.5 = meio-dia, 0.75 = 18:00, etc
                total_seconds = int(time_value * 24 * 60 * 60)
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                microseconds = int((time_value * 24 * 60 * 60 * 1000000) % 1000000)
                
                result = datetime.combine(
                    now_date.date(),
                    dt_time(hours, minutes, seconds, microseconds)
                )
            
            # Se é string, tenta vários formatos
            elif isinstance(time_value, str):
                time_str = str(time_value).strip()
                
                # Formatos possíveis de tempo
                formats = [
                    '%H:%M:%S.%f',  # 09:15:30.123
                    '%H:%M:%S',     # 09:15:30
                    '%H:%M',        # 09:15
                    '%I:%M:%S %p',  # 09:15:30 AM
                    '%I:%M %p',     # 09:15 AM
                ]
                
                for fmt in formats:
                    try:
                        parsed_time = datetime.strptime(time_str, fmt).time()
                        result = datetime.combine(now_date.date(), parsed_time)
                        break
                    except ValueError:
                        continue
            
            # Se nenhum método funcionou, usa fallback
            if result is None:
                # Cria timestamp incremental baseado no índice
                milliseconds = row_index % 1000
                seconds = (row_index // 1000) % 60
                result = now_date.replace(microsecond=milliseconds * 1000)
                logger.debug(f"Usando fallback timestamp para valor: {time_value}")
            
            # Salva no cache
            self._timestamp_cache[cache_key] = result
            
            # Limpa cache se ficar muito grande
            if len(self._timestamp_cache) > 10000:
                self._timestamp_cache.clear()
            
            return result
            
        except Exception as e:
            logger.warning(f"Erro ao parsear tempo '{time_value}': {e}")
            # Fallback final
            return now_date.replace(microsecond=row_index * 1000)

    def _read_trades(self, symbol: str) -> List[Trade]:
        """
        Lê trades do Excel com timestamps reais (FASE 3.1).
        """
        if not self.sheet:
            return []
            
        try:
            trade_config = self.config[symbol]['trades']
            column_map = trade_config['columns'] 
            data = self.sheet.range(trade_config['range']).value
            
            if not data:
                logger.debug(f"Sem dados de trades para {symbol}")
                return []
            
            trades = []
            now = datetime.now()
            
            for idx, row in enumerate(data):
                if row is None or row[0] is None:
                    continue
                
                try:
                    # Valida se há dados suficientes na linha
                    if len(row) <= max(column_map.values()):
                        continue
                    
                    # Extrai valores usando mapeamento de colunas
                    time_value = row[column_map['time']]
                    side_value = row[column_map['side']]
                    price_value = row[column_map['price']]
                    volume_value = row[column_map['volume']]
                    
                    # Valida valores obrigatórios
                    if price_value is None or volume_value is None:
                        continue
                    
                    # Converte valores
                    price = float(price_value)
                    volume = int(volume_value)
                    
                    # Só adiciona se preço E volume forem maiores que zero
                    if price > 0 and volume > 0:
                        # FASE 3.1: Parse timestamp real
                        timestamp = self._parse_time(time_value, now, idx)
                        
                        # Garante formato de time_str consistente
                        time_str = timestamp.strftime('%H:%M:%S.%f')[:-3]  # Remove últimos 3 dígitos dos microsegundos
                        
                        trades.append(Trade(
                            symbol=symbol,
                            time_str=time_str,
                            side=self._normalize_side(side_value),
                            price=price,
                            volume=volume,
                            timestamp=timestamp  # Agora usa timestamp real!
                        ))
                        
                except (ValueError, TypeError, IndexError) as e:
                    logger.debug(f"Erro ao processar linha {idx} de {symbol}: {e}")
                    continue
            
            # Ordena trades por timestamp para garantir ordem cronológica
            trades.sort(key=lambda t: t.timestamp)
            
            logger.debug(f"Lidos {len(trades)} trades válidos para {symbol} com timestamps reais")
            return trades
            
        except Exception as e:
            logger.error(f"Erro ao ler trades de {symbol}: {e}", exc_info=True)
            return []

    def _read_book(self, symbol: str) -> OrderBook:
        """Lê book do Excel de acordo com as configurações."""
        if not self.sheet:
            return OrderBook()
            
        try:
            book_config = self.config[symbol]['book']
            
            # Lê dados de BID
            bid_data = self.sheet.range(book_config['bid_range']).value
            bids = []
            
            if bid_data:
                for r in bid_data:
                    if r and len(r) >= 4 and r[3] is not None:  # Preço está na coluna 3 (0-indexed)
                        try:
                            price = float(r[3])
                            volume = int(r[2] or 0)  # Volume está na coluna 2
                            # Só adiciona se o preço for maior que 0
                            if price > 0:
                                bids.append(BookLevel(price=price, volume=volume))
                        except (ValueError, TypeError):
                            continue
            
            # Lê dados de ASK
            ask_data = self.sheet.range(book_config['ask_range']).value
            asks = []
            
            if ask_data:
                for r in ask_data:
                    if r and r[0] is not None:  # Preço está na coluna 0
                        try:
                            price = float(r[0])
                            volume = int(r[1] or 0) if len(r) > 1 else 0  # Volume está na coluna 1
                            # Só adiciona se o preço for maior que 0
                            if price > 0:
                                asks.append(BookLevel(price=price, volume=volume))
                        except (ValueError, TypeError):
                            continue
            
            return OrderBook(bids=bids, asks=asks)
            
        except Exception as e:
            logger.error(f"Erro ao ler book de {symbol}: {e}", exc_info=True)
            return OrderBook()

    def _normalize_side(self, side_str: str) -> TradeSide:
        """Normaliza o lado da negociação."""
        if not side_str:
            return TradeSide.UNKNOWN
            
        side_upper = str(side_str).upper()
        
        # Tenta várias variações
        if any(x in side_upper for x in ['COMPRADOR', 'COMPRA', 'BUY', 'C']):
            return TradeSide.BUY
        elif any(x in side_upper for x in ['VENDEDOR', 'VENDA', 'SELL', 'V']):
            return TradeSide.SELL
            
        return TradeSide.UNKNOWN
        
    def _calculate_mid_price(self, book: OrderBook) -> float:
        """Calcula o preço médio do book."""
        if book.best_bid > 0 and book.best_ask > 0:
            return (book.best_bid + book.best_ask) / 2
        elif book.best_bid > 0:
            return book.best_bid
        elif book.best_ask > 0:
            return book.best_ask
        return 0.0

    def close(self) -> None:
        """Fecha a conexão com o Excel."""
        self.connected = False
        # Limpa cache de timestamps
        self._timestamp_cache.clear()
        # Não fecha o workbook para manter o Excel aberto
        self.wb = None
        self.sheet = None
        logger.info("Conexão com Excel fechada (arquivo mantido aberto)")

    def get_status(self) -> Dict[str, Any]:
        """Retorna status da conexão."""
        return {
            'connected': self.connected,
            'file': self.file_path,
            'sheet': self.sheet_name,
            'has_workbook': self.wb is not None,
            'has_sheet': self.sheet is not None,
            'timestamp_cache_size': len(self._timestamp_cache)
        }