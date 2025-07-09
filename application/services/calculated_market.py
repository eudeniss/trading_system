# application/services/calculated_market.py
"""
Analisador de Mercado Calculado (Frajola) - Clean Architecture
Calcula níveis baseados em PTAX e cupom cambial com suporte para backtesting
"""
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List, Any
from dataclasses import dataclass
from pathlib import Path

from core.entities.signal import Signal, SignalSource, SignalLevel

logger = logging.getLogger(__name__)


@dataclass
class CalculatedLevel:
    """Representa um nível calculado do mercado."""
    name: str
    price: float
    type: str  # 'RESISTENCIA', 'SUPORTE', 'PIVOT'
    strength: int  # 0-3
    distance: Optional[float] = None
    position: Optional[str] = None  # 'ACIMA', 'ABAIXO'


class CalculatedMarketAnalyzer:
    """
    Analisador que calcula níveis de mercado baseados em PTAX.
    Implementa a matriz de confluência completa do roadmap.
    """
    
    def __init__(self, config: Dict[str, Any], target_date: Optional[datetime] = None):
        """
        Inicializa o analisador com configurações.
        
        Args:
            config: Configurações do sistema
            target_date: Data alvo para backtesting (None = ao vivo)
        """
        self.config = config.get('calculated_market', {})
        self.target_date = target_date
        
        # Parâmetros do cálculo
        self.ptax_api_url = self.config.get(
            'ptax_api_url', 
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados/ultimos/5?formato=json"
        )
        self.cupom_cambial = self.config.get('cupom_cambial', 25)
        self.volatilidade_unidade = self.config.get('volatilidade_unidade', 12.5)
        self.tolerancia_proximidade = self.config.get('tolerancia_proximidade', 3.0)
        
        # Multiplicadores dos níveis (do roadmap)
        self.multiplicadores = {
            'SOFRER_2X': 1.60,
            'SOFRER': 1.25,
            'SX_SUP': 0.80,
            'DEFENDO': 0.45,
            'BASE': 0.00,  # PIVOT = BASE = Valor Justo
            'PB': -0.45,   # Primeiro suporte
            'SX': -0.80,
            'DEVENDO': -1.25,
            'SOFGRE': -1.60
        }
        
        # Janelas PTAX
        self.janelas_ptax = [
            (datetime.strptime('10:00', '%H:%M').time(), datetime.strptime('10:10', '%H:%M').time()),
            (datetime.strptime('11:00', '%H:%M').time(), datetime.strptime('11:10', '%H:%M').time()),
            (datetime.strptime('12:00', '%H:%M').time(), datetime.strptime('12:10', '%H:%M').time()),
            (datetime.strptime('13:00', '%H:%M').time(), datetime.strptime('13:10', '%H:%M').time())
        ]
        
        # Matriz de confluência completa do roadmap
        self._init_confluence_matrix()
        
        # Estado interno
        self.niveis_calculados: Dict[str, CalculatedLevel] = {}
        self.valor_justo: float = 0.0
        self.ultima_atualizacao: Optional[datetime] = None
        self.logs_dir = Path(self.config.get('logs_dir', 'logs'))
        self.logs_dir.mkdir(exist_ok=True)
        
        # Calcula níveis na inicialização
        self._calculate_daily_levels()
    
    def _init_confluence_matrix(self):
        """
        Inicializa a matriz de confluência completa do roadmap.
        20 combinações que geram sinais $ (10 compra + 10 venda).
        """
        self.matriz_confluencia = {
            # 🟢 SINAIS DE COMPRA (10 combinações)
            ('ABSORCAO_COMPRADORA', 'DEVENDO'): {
                'acao': 'COMPRA', 'confianca': 0.85, 'desc': 'Absorção em suporte forte'
            },
            ('ABSORCAO_COMPRADORA', 'SOFGRE'): {
                'acao': 'COMPRA', 'confianca': 0.90, 'desc': 'Absorção em suporte extremo'
            },
            ('ABSORCAO_COMPRADORA', 'PB'): {  # PB = SUPORTE no roadmap
                'acao': 'COMPRA', 'confianca': 0.75, 'desc': 'Absorção em suporte primário'
            },
            ('EXAUSTAO_VENDEDORA', 'DEVENDO'): {
                'acao': 'COMPRA', 'confianca': 0.80, 'desc': 'Exaustão vendedora em suporte'
            },
            ('EXAUSTAO_VENDEDORA', 'SOFGRE'): {
                'acao': 'COMPRA', 'confianca': 0.85, 'desc': 'Exaustão vendedora extrema'
            },
            ('ICEBERG_COMPRADOR', 'DEVENDO'): {
                'acao': 'COMPRA', 'confianca': 0.85, 'desc': 'Iceberg comprador em suporte forte'
            },
            ('ICEBERG_COMPRADOR', 'PB'): {
                'acao': 'COMPRA', 'confianca': 0.75, 'desc': 'Iceberg comprador em suporte'
            },
            ('VOLUME_SPREAD_COMPRA', 'DEVENDO'): {
                'acao': 'COMPRA', 'confianca': 0.80, 'desc': 'Volume spread positivo em suporte'
            },
            ('TRAP', 'DEVENDO'): {
                'acao': 'COMPRA', 'confianca': 0.85, 'desc': 'Armadilha de baixa em suporte forte'
            },
            ('SQUEEZE', 'SOFGRE'): {
                'acao': 'COMPRA', 'confianca': 0.90, 'desc': 'Squeeze de baixa em suporte extremo'
            },
            
            # 🔴 SINAIS DE VENDA (10 combinações)
            ('ABSORCAO_VENDEDORA', 'SOFRER'): {
                'acao': 'VENDA', 'confianca': 0.85, 'desc': 'Absorção em resistência forte'
            },
            ('ABSORCAO_VENDEDORA', 'SOFRER_2X'): {
                'acao': 'VENDA', 'confianca': 0.90, 'desc': 'Absorção em resistência extrema'
            },
            ('ABSORCAO_VENDEDORA', 'DEFENDO'): {
                'acao': 'VENDA', 'confianca': 0.75, 'desc': 'Absorção em resistência primária'
            },
            ('EXAUSTAO_COMPRADORA', 'SOFRER'): {
                'acao': 'VENDA', 'confianca': 0.80, 'desc': 'Exaustão compradora em resistência'
            },
            ('EXAUSTAO_COMPRADORA', 'SOFRER_2X'): {
                'acao': 'VENDA', 'confianca': 0.85, 'desc': 'Exaustão compradora extrema'
            },
            ('ICEBERG_VENDEDOR', 'DEFENDO'): {
                'acao': 'VENDA', 'confianca': 0.75, 'desc': 'Iceberg vendedor em resistência'
            },
            ('ICEBERG_VENDEDOR', 'SOFRER'): {
                'acao': 'VENDA', 'confianca': 0.80, 'desc': 'Iceberg vendedor em resistência forte'
            },
            ('VOLUME_SPREAD_VENDA', 'SOFRER'): {
                'acao': 'VENDA', 'confianca': 0.80, 'desc': 'Volume spread negativo em resistência'
            },
            ('TRAP', 'SOFRER'): {
                'acao': 'VENDA', 'confianca': 0.85, 'desc': 'Armadilha de alta em resistência forte'
            },
            ('SQUEEZE', 'SOFRER_2X'): {
                'acao': 'VENDA', 'confianca': 0.90, 'desc': 'Squeeze de alta em resistência extrema'
            }
        }
    
    def _calculate_daily_levels(self) -> bool:
        """
        Calcula os níveis do dia baseados na PTAX.
        Se target_date estiver definida, busca PTAX histórica.
        """
        try:
            logger.info("🧮 Calculando níveis do mercado calculado (Frajola)...")
            
            # Busca PTAX
            if self.target_date:
                ptax = self._fetch_historical_ptax(self.target_date)
            else:
                ptax = self._fetch_current_ptax()
            
            if not ptax:
                logger.error("Falha ao obter PTAX")
                return False
            
            # Calcula valor justo
            self.valor_justo = (ptax * 1000) + self.cupom_cambial
            
            # Calcula cada nível
            self.niveis_calculados.clear()
            
            for nome, multiplicador in self.multiplicadores.items():
                preco = self.valor_justo + (multiplicador * self.volatilidade_unidade)
                
                # Determina tipo do nível
                if multiplicador > 0:
                    tipo = 'RESISTENCIA'
                elif multiplicador < 0:
                    tipo = 'SUPORTE'
                else:
                    tipo = 'PIVOT'
                
                # Cria nível calculado
                self.niveis_calculados[nome] = CalculatedLevel(
                    name=nome,
                    price=round(preco, 2),
                    type=tipo,
                    strength=min(abs(int(multiplicador * 2)), 3)  # 0-3
                )
            
            self.ultima_atualizacao = datetime.now()
            
            # Salva em arquivo JSON
            self._save_levels_to_file()
            
            # Log dos níveis calculados
            logger.info(f"📊 Valor Justo (BASE): {self.valor_justo:.2f}")
            logger.info("📈 Níveis calculados:")
            for nome, nivel in sorted(
                self.niveis_calculados.items(), 
                key=lambda x: x[1].price, 
                reverse=True
            ):
                emoji = "🔴" if nivel.type == "RESISTENCIA" else "🟢" if nivel.type == "SUPORTE" else "🟡"
                logger.info(f"  {emoji} {nome:10} {nivel.price:>8.2f} ({nivel.type})")
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao calcular níveis: {e}", exc_info=True)
            return False
    
    def _fetch_current_ptax(self) -> Optional[float]:
        """Busca o valor atual da PTAX do BCB."""
        try:
            response = requests.get(self.ptax_api_url, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            if data and len(data) > 0:
                # Pega o valor mais recente
                latest = data[-1]
                ptax = float(latest['valor'])
                logger.info(f"💱 PTAX atual obtida: {ptax:.4f}")
                return ptax
                
        except requests.RequestException as e:
            logger.error(f"Erro ao buscar PTAX: {e}")
        except (KeyError, ValueError, IndexError) as e:
            logger.error(f"Erro ao processar resposta da PTAX: {e}")
        
        # Valor padrão se falhar
        default_ptax = 5.45
        logger.warning(f"⚠️ Usando PTAX padrão: {default_ptax}")
        return default_ptax
    
    def _fetch_historical_ptax(self, target_date: datetime) -> Optional[float]:
        """
        Busca PTAX histórica para backtesting.
        Usa a PTAX do dia anterior à data alvo.
        """
        try:
            # Busca PTAX do dia anterior
            previous_date = target_date - timedelta(days=1)
            
            # Ajusta URL para buscar data específica
            date_str = previous_date.strftime('%d/%m/%Y')
            historical_url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados?formato=json&dataInicial={date_str}&dataFinal={date_str}"
            
            logger.info(f"🔄 Buscando PTAX histórica de {date_str} para replay de {target_date.strftime('%d/%m/%Y')}")
            
            response = requests.get(historical_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data and len(data) > 0:
                ptax = float(data[0]['valor'])
                logger.info(f"💱 PTAX histórica obtida: {ptax:.4f} ({date_str})")
                return ptax
            else:
                logger.warning(f"⚠️ Sem dados de PTAX para {date_str}")
                
        except Exception as e:
            logger.error(f"Erro ao buscar PTAX histórica: {e}")
        
        # Se falhar, tenta API principal
        logger.info("Tentando API principal de PTAX...")
        return self._fetch_current_ptax()
    
    def _save_levels_to_file(self):
        """Salva os níveis calculados em arquivo JSON."""
        try:
            # Define nome do arquivo baseado na data
            if self.target_date:
                file_name = f"calculated_levels_{self.target_date.strftime('%Y%m%d')}.json"
            else:
                file_name = f"calculated_levels_{datetime.now().strftime('%Y%m%d')}.json"
            
            data = {
                'data_calculo': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_alvo': self.target_date.strftime('%Y-%m-%d') if self.target_date else 'AO_VIVO',
                'valor_justo': round(self.valor_justo, 2),
                'cupom_cambial': self.cupom_cambial,
                'volatilidade': self.volatilidade_unidade,
                'niveis': {
                    nome: {
                        'preco': nivel.price,
                        'tipo': nivel.type,
                        'forca': nivel.strength
                    }
                    for nome, nivel in self.niveis_calculados.items()
                }
            }
            
            json_file = self.logs_dir / file_name
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            logger.debug(f"📁 Níveis salvos em {json_file}")
            
        except Exception as e:
            logger.error(f"Erro ao salvar níveis: {e}")
    
    def check_proximity(self, price: float) -> Optional[Tuple[str, CalculatedLevel]]:
        """
        Verifica se o preço está próximo de algum nível calculado.
        
        Args:
            price: Preço atual
            
        Returns:
            Tupla (nome_nivel, nivel) se houver proximidade, None caso contrário
        """
        for nome, nivel in self.niveis_calculados.items():
            distancia = abs(price - nivel.price)
            
            if distancia <= self.tolerancia_proximidade:
                # Atualiza informações de proximidade
                nivel.distance = distancia
                nivel.position = 'ACIMA' if price > nivel.price else 'ABAIXO'
                return (nome, nivel)
        
        return None
    
    def is_ptax_window(self, timestamp: datetime = None) -> bool:
        """
        Verifica se está dentro de uma janela PTAX.
        
        Args:
            timestamp: Momento a verificar (padrão: agora)
            
        Returns:
            True se está em janela PTAX
        """
        if timestamp is None:
            timestamp = datetime.now()
            
        current_time = timestamp.time()
        
        for inicio, fim in self.janelas_ptax:
            if inicio <= current_time <= fim:
                return True
        
        return False
    
    def analyze_confluence(self, tape_pattern: str, price: float, symbol: str = 'WDO',
                         strength: int = 5, volume: int = 0,
                         timestamp: datetime = None) -> Optional[Signal]:
        """
        Analisa confluência entre padrão do tape e níveis calculados.
        Implementa a matriz completa do roadmap.
        
        Args:
            tape_pattern: Padrão detectado pelo tape reading
            price: Preço atual
            symbol: Símbolo do ativo
            strength: Força do sinal (1-10)
            volume: Volume da operação
            timestamp: Momento do sinal
            
        Returns:
            Signal de confluência ($) se houver, None caso contrário
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Verifica proximidade com níveis
        proximity = self.check_proximity(price)
        if not proximity:
            return None
        
        level_name, level_info = proximity
        
        # Normaliza nome do padrão para a matriz
        pattern_normalized = self._normalize_pattern_name(tape_pattern)
        
        # Busca na matriz de confluência
        confluence_key = (pattern_normalized, level_name)
        confluence_data = self.matriz_confluencia.get(confluence_key)
        
        # Condições especiais do roadmap
        if not confluence_data:
            # Força ≥9 + Nível Extremo sempre gera $
            if strength >= 9 and level_name in ['SOFRER_2X', 'SOFGRE']:
                action = 'VENDA' if level_name == 'SOFRER_2X' else 'COMPRA'
                confluence_data = {
                    'acao': action,
                    'confianca': 0.85,
                    'desc': 'Força extrema em nível extremo'
                }
        
        # Precisa de força mínima 7 e confluência válida
        if confluence_data and strength >= 7:
            # Confiança mínima de 65%
            if confluence_data['confianca'] >= 0.65:
                return self._create_confluence_signal(
                    tape_pattern=tape_pattern,
                    price=price,
                    symbol=symbol,
                    level_name=level_name,
                    level_info=level_info,
                    confluence_data=confluence_data,
                    strength=strength,
                    volume=volume,
                    timestamp=timestamp
                )
        
        return None
    
    def _normalize_pattern_name(self, pattern: str) -> str:
        """Normaliza nome do padrão para compatibilidade com a matriz."""
        # Mapeamento dos padrões do tape reading para a matriz
        pattern_map = {
            # Padrões principais
            'ABSORPTION_DETECTED': 'ABSORCAO_COMPRADORA',
            'ESCORA_DETECTADA': 'ABSORCAO_COMPRADORA',
            'PRESSAO_COMPRA': 'VOLUME_SPREAD_COMPRA',
            'PRESSAO_VENDA': 'VOLUME_SPREAD_VENDA',
            'MOMENTUM_EXTREMO': 'SQUEEZE',
            'EXHAUSTION_DETECTED': 'EXAUSTAO_VENDEDORA',
            'SELLING_EXHAUSTION': 'EXAUSTAO_VENDEDORA',
            'BUYING_EXHAUSTION': 'EXAUSTAO_COMPRADORA',
            'ICEBERG_BUY': 'ICEBERG_COMPRADOR',
            'ICEBERG_SELL': 'ICEBERG_VENDEDOR',
            'TRAP_DETECTED': 'TRAP',
            'VOLUME_IMBALANCE': 'VOLUME_SPREAD_COMPRA',
            
            # Adicione outros mapeamentos conforme necessário
        }
        
        # Tenta mapear ou retorna o padrão original em maiúsculas
        normalized = pattern_map.get(pattern.upper())
        if normalized:
            return normalized
        
        # Tenta inferir pelo nome
        pattern_upper = pattern.upper()
        if 'COMPRA' in pattern_upper or 'BUY' in pattern_upper:
            if 'ABSORCAO' in pattern_upper or 'ABSORPTION' in pattern_upper:
                return 'ABSORCAO_COMPRADORA'
            elif 'ICEBERG' in pattern_upper:
                return 'ICEBERG_COMPRADOR'
        elif 'VENDA' in pattern_upper or 'SELL' in pattern_upper:
            if 'ABSORCAO' in pattern_upper or 'ABSORPTION' in pattern_upper:
                return 'ABSORCAO_VENDEDORA'
            elif 'ICEBERG' in pattern_upper:
                return 'ICEBERG_VENDEDOR'
        
        return pattern_upper
    
    def _create_confluence_signal(self, tape_pattern: str, price: float, symbol: str,
                                level_name: str, level_info: CalculatedLevel,
                                confluence_data: Dict, strength: int,
                                volume: int, timestamp: datetime) -> Signal:
        """
        Cria sinal de alta confluência seguindo o formato do roadmap.
        """
        action = confluence_data['acao']
        confidence = confluence_data['confianca']
        description = confluence_data['desc']
        
        # Define stops e alvos
        if action == 'COMPRA':
            stop = level_info.price - 5.0
            # Encontra próxima resistência como alvo
            target = self._find_next_resistance(price)
            action_desc = "COMPRA CONFIRMADA"
            emoji = "🟢"
        else:  # VENDA
            stop = level_info.price + 5.0
            # Encontra próximo suporte como alvo
            target = self._find_next_support(price)
            action_desc = "VENDA CONFIRMADA"
            emoji = "🔴"
        
        # Ajusta confiança se estiver em janela PTAX (+10%)
        is_ptax = self.is_ptax_window(timestamp)
        if is_ptax:
            confidence = min(confidence + 0.1, 0.95)
        
        # Formata mensagem seguindo o padrão do roadmap
        lines = [
            f"{'═' * 60}",
            f"$ {emoji} {action_desc} - {level_name} {level_info.price:.2f} $ {symbol}",
            f"Tape: {self._format_pattern_name(tape_pattern)} [Força: {strength}/10]",
            f"Frajola: {description}",
            f"Stop: {stop:.2f} | Alvo: {target:.2f}"
        ]
        
        # Condições especiais
        if volume > 1000:
            lines.append(f"Volume: {volume:,} (alto)")
        
        if is_ptax:
            lines.append("⏰ JANELA PTAX ATIVA")
        
        lines.append(f"Confiança: {int(confidence * 100)}%")
        lines.append(f"{'═' * 60}")
        
        message = "\n".join(lines)
        
        # Cria sinal de alta confluência
        return Signal(
            source=SignalSource.CONFLUENCE,
            level=SignalLevel.ALERT,
            message=message,
            details={
                'symbol': symbol,
                'pattern': tape_pattern,
                'price': price,
                'level': level_name,
                'level_price': level_info.price,
                'action': action,
                'confidence': confidence,
                'stop': stop,
                'target': target,
                'strength': strength,
                'volume': volume,
                'is_ptax_window': is_ptax,
                'confluence_type': 'FRAJOLA',
                'timestamp': timestamp
            }
        )
    
    def _find_next_resistance(self, price: float) -> float:
        """Encontra próxima resistência acima do preço."""
        resistances = [
            level.price for level in self.niveis_calculados.values()
            if level.price > price and level.type == 'RESISTENCIA'
        ]
        
        if resistances:
            return min(resistances)
        
        # Se não houver, retorna valor justo + 20 pontos
        return self.valor_justo + 20.0
    
    def _find_next_support(self, price: float) -> float:
        """Encontra próximo suporte abaixo do preço."""
        supports = [
            level.price for level in self.niveis_calculados.values()
            if level.price < price and level.type == 'SUPORTE'
        ]
        
        if supports:
            return max(supports)
        
        # Se não houver, retorna valor justo - 20 pontos
        return self.valor_justo - 20.0
    
    def _format_pattern_name(self, pattern: str) -> str:
        """Formata nome do padrão para exibição."""
        format_map = {
            'ABSORCAO_COMPRADORA': 'Absorção Compradora',
            'ABSORCAO_VENDEDORA': 'Absorção Vendedora',
            'EXAUSTAO_COMPRADORA': 'Exaustão Compradora',
            'EXAUSTAO_VENDEDORA': 'Exaustão Vendedora',
            'ICEBERG_COMPRADOR': 'Iceberg Comprador',
            'ICEBERG_VENDEDOR': 'Iceberg Vendedor',
            'VOLUME_SPREAD_COMPRA': 'Volume Spread Positivo',
            'VOLUME_SPREAD_VENDA': 'Volume Spread Negativo',
            'TRAP': 'Armadilha (Trap)',
            'SQUEEZE': 'Squeeze',
            'ESCORA_DETECTADA': 'Escora Detectada',
            'PRESSAO_COMPRA': 'Pressão Compradora',
            'PRESSAO_VENDA': 'Pressão Vendedora',
            'MOMENTUM_EXTREMO': 'Momentum Extremo',
            'ABSORPTION_DETECTED': 'Absorção Detectada',
            'EXHAUSTION_DETECTED': 'Exaustão Detectada'
        }
        
        # Tenta formatar ou usa o padrão com espaços
        return format_map.get(pattern.upper(), pattern.replace('_', ' ').title())
    
    def get_current_levels(self) -> Dict[str, CalculatedLevel]:
        """Retorna os níveis calculados atuais."""
        return self.niveis_calculados.copy()
    
    def get_fair_value(self) -> float:
        """Retorna o valor justo (BASE) calculado."""
        return self.valor_justo
    
    def refresh_levels(self) -> bool:
        """
        Força recálculo dos níveis.
        
        Returns:
            True se recalculou com sucesso
        """
        logger.info("🔄 Forçando recálculo dos níveis...")
        return self._calculate_daily_levels()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas do analisador."""
        return {
            'valor_justo': self.valor_justo,
            'ultima_atualizacao': self.ultima_atualizacao.isoformat() if self.ultima_atualizacao else None,
            'modo': 'REPLAY' if self.target_date else 'AO_VIVO',
            'data_alvo': self.target_date.isoformat() if self.target_date else None,
            'total_niveis': len(self.niveis_calculados),
            'niveis': {
                nome: {
                    'preco': nivel.price,
                    'tipo': nivel.type,
                    'forca': nivel.strength
                }
                for nome, nivel in self.niveis_calculados.items()
            }
        }