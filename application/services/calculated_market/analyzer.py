# application/services/calculated_market/analyzer.py
"""
Analisador principal que orquestra todos os componentes do Mercado Calculado.
"""
import json
import logging
from datetime import datetime, time
from pathlib import Path
from typing import Dict, Optional, Any, Tuple, List

from .ptax_fetcher import PtaxFetcher
from .level_calculator import LevelCalculator, CalculatedLevel
from .confluence_matrix import ConfluenceMatrix
from core.entities.signal import Signal, SignalSource, SignalLevel

logger = logging.getLogger(__name__)


class CalculatedMarketAnalyzer:
    """
    Analisador que orquestra o cálculo de níveis e a análise de confluência
    usando componentes modularizados.
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
        
        # Parâmetros gerais
        self.tolerancia_proximidade = self.config.get('tolerancia_proximidade', 3.0)
        
        # Instancia os componentes modulares
        self.ptax_fetcher = PtaxFetcher(self.config)
        self.level_calculator = LevelCalculator(self.config)
        self.matrix = ConfluenceMatrix(self.config)
        
        # Janelas PTAX
        self.janelas_ptax = self._parse_ptax_windows()
        
        # Estado interno
        self.niveis_calculados: Dict[str, CalculatedLevel] = {}
        self.valor_justo: float = 0.0
        self.ultima_atualizacao: Optional[datetime] = None
        
        # Diretório de logs
        self.logs_dir = Path(self.config.get('logs_dir', 'logs'))
        self.logs_dir.mkdir(exist_ok=True)
        
        # Calcula níveis na inicialização
        self._calculate_daily_levels()

    def _parse_ptax_windows(self) -> List[Tuple[time, time]]:
        """Converte as janelas PTAX do config para objetos time."""
        windows_config = self.config.get('janelas_ptax', [
            ['10:00', '10:10'],
            ['11:00', '11:10'],
            ['12:00', '12:10'],
            ['13:00', '13:10']
        ])
        
        windows = []
        for start_str, end_str in windows_config:
            start = datetime.strptime(start_str, '%H:%M').time()
            end = datetime.strptime(end_str, '%H:%M').time()
            windows.append((start, end))
        
        return windows

    def _calculate_daily_levels(self) -> bool:
        """
        Orquestra a busca de PTAX e o cálculo dos níveis.
        
        Returns:
            True se calculou com sucesso
        """
        try:
            logger.info("🧮 Calculando níveis do mercado calculado (Frajola)...")
            
            # Busca PTAX através do componente especializado
            ptax = self.ptax_fetcher.fetch_ptax(self.target_date)
            
            if not ptax:
                logger.error("❌ Falha ao obter PTAX para cálculo dos níveis")
                return False
            
            # Calcula níveis através do componente especializado
            self.valor_justo, self.niveis_calculados = self.level_calculator.calculate(ptax)
            
            if not self.niveis_calculados:
                logger.error("❌ Falha ao calcular níveis")
                return False
            
            self.ultima_atualizacao = datetime.now()
            
            # Salva em arquivo JSON para auditoria
            self._save_levels_to_file()
            
            # Log dos níveis calculados
            self._log_calculated_levels()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao calcular níveis: {e}", exc_info=True)
            return False

    def _save_levels_to_file(self):
        """Salva os níveis calculados em arquivo JSON para auditoria."""
        try:
            # Define nome do arquivo baseado na data
            if self.target_date:
                file_name = f"calculated_levels_{self.target_date.strftime('%Y%m%d')}.json"
            else:
                file_name = f"calculated_levels_{datetime.now().strftime('%Y%m%d')}.json"
            
            data = {
                'data_calculo': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_alvo': self.target_date.strftime('%Y-%m-%d') if self.target_date else 'AO_VIVO',
                'valor_justo': self.valor_justo,
                'parametros': {
                    'cupom_cambial': self.level_calculator.cupom_cambial,
                    'volatilidade': self.level_calculator.volatilidade_unidade,
                    'tolerancia_proximidade': self.tolerancia_proximidade
                },
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

    def _log_calculated_levels(self):
        """Loga os níveis calculados de forma organizada."""
        logger.info(f"📊 Valor Justo (BASE): {self.valor_justo:.2f}")
        logger.info("📈 Níveis calculados:")
        
        # Ordena por preço (maior para menor)
        sorted_levels = sorted(
            self.niveis_calculados.items(), 
            key=lambda x: x[1].price, 
            reverse=True
        )
        
        for nome, nivel in sorted_levels:
            emoji = "🔴" if nivel.type == "RESISTENCIA" else "🟢" if nivel.type == "SUPORTE" else "🟡"
            logger.info(f"  {emoji} {nome:10} {nivel.price:>8.2f} ({nivel.type})")

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
                         timestamp: datetime = None, **kwargs) -> Optional[Signal]:
        """
        Analisa confluência entre padrão do tape e níveis calculados.
        
        Args:
            tape_pattern: Padrão detectado pelo tape reading
            price: Preço atual
            symbol: Símbolo do ativo
            strength: Força do sinal (1-10)
            volume: Volume da operação
            timestamp: Momento do sinal
            **kwargs: Detalhes adicionais do sinal (incluindo 'direction')
            
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
        
        # Normaliza nome do padrão (agora é simples)
        pattern_normalized = self._normalize_pattern_name(tape_pattern)
        
        # Extrai direção do sinal se disponível
        signal_direction = kwargs.get('direction', '')
        
        # Busca regra na matriz considerando direção
        rule = self.matrix.find_rule(pattern_normalized, level_name, signal_direction)
        
        # Se não encontrou, verifica condições especiais
        if not rule:
            rule = self.matrix.check_extreme_conditions(strength, level_name)
        
        # Valida se o sinal atende aos critérios
        if self.matrix.is_valid_signal(rule, strength):
            return self._create_confluence_signal(
                tape_pattern=tape_pattern,
                price=price,
                symbol=symbol,
                level_name=level_name,
                level_info=level_info,
                rule=rule,
                strength=strength,
                volume=volume,
                timestamp=timestamp,
                **kwargs
            )
        
        return None

    def _normalize_pattern_name(self, pattern: str) -> str:
        """
        Normaliza nome do padrão simplesmente convertendo para maiúsculas.
        Sistema 100% previsível - o que entra é o que é usado.
        
        Args:
            pattern: Nome do padrão
            
        Returns:
            Padrão em maiúsculas
        """
        if not pattern:
            return "UNKNOWN"
        return pattern.upper()

    def _create_confluence_signal(self, tape_pattern: str, price: float, symbol: str,
                                level_name: str, level_info: CalculatedLevel,
                                rule: Dict, strength: int,
                                volume: int, timestamp: datetime, **kwargs) -> Signal:
        """
        Cria sinal de alta confluência seguindo o formato do roadmap.
        
        Args:
            Todos os dados necessários para construir o sinal
            
        Returns:
            Signal formatado
        """
        action = rule['acao']
        confidence = rule['confianca']
        description = rule['desc']
        
        # Calcula stops e alvos através do componente
        stop, target = self.level_calculator.calculate_stops_and_targets(
            action, price, self.niveis_calculados
        )
        
        # Ajusta confiança se estiver em janela PTAX (+10%)
        is_ptax = self.is_ptax_window(timestamp)
        if is_ptax:
            confidence = min(confidence + 0.1, 0.95)
        
        # Define emoji e descrição da ação
        if action == 'COMPRA':
            emoji = "🟢"
            action_desc = "COMPRA CONFIRMADA"
        else:
            emoji = "🔴"
            action_desc = "VENDA CONFIRMADA"
        
        # Formata mensagem seguindo o padrão do roadmap
        lines = [
            f"{'═' * 60}",
            f"$ {emoji} {action_desc} - {level_name} {level_info.price:.2f} $ {symbol}",
            f"Tape: {self._format_pattern_name(tape_pattern)} [Força: {strength}/10]",
            f"Frajola: {description}",
            f"Stop: {stop:.2f} | Alvo: {target:.2f}"
        ]
        
        # Adiciona informações extras se relevantes
        if volume > 1000:
            lines.append(f"Volume: {volume:,} (alto)")
        
        if is_ptax:
            lines.append("⏰ JANELA PTAX ATIVA")
        
        # Adiciona direção se disponível
        direction = kwargs.get('direction', '')
        if direction:
            lines.append(f"Direção do Sinal: {direction}")
        
        lines.append(f"Confiança: {int(confidence * 100)}%")
        lines.append(f"{'═' * 60}")
        
        message = "\n".join(lines)
        
        # Monta detalhes completos do sinal
        details = {
            'symbol': symbol,
            'pattern': tape_pattern,
            'pattern_normalized': self._normalize_pattern_name(tape_pattern),
            'price': price,
            'level': level_name,
            'level_price': level_info.price,
            'level_type': level_info.type,
            'action': action,
            'confidence': confidence,
            'stop': stop,
            'target': target,
            'strength': strength,
            'volume': volume,
            'is_ptax_window': is_ptax,
            'confluence_type': 'FRAJOLA',
            'timestamp': timestamp,
            'rule_applied': rule
        }
        
        # Adiciona kwargs extras aos detalhes
        details.update(kwargs)
        
        # Cria sinal de alta confluência
        return Signal(
            source=SignalSource.CONFLUENCE,
            level=SignalLevel.ALERT,
            message=message,
            details=details
        )

    def _format_pattern_name(self, pattern: str) -> str:
        """
        Formata nome do padrão para exibição amigável.
        
        Args:
            pattern: Nome do padrão em maiúsculas
            
        Returns:
            Nome formatado para exibição
        """
        format_map = {
            # Padrões básicos
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
            
            # Padrões adicionais
            'MOMENTUM_EXTREMO': 'Momentum Extremo',
            'DIVERGENCIA_ALTA': 'Divergência Altista',
            'DIVERGENCIA_BAIXA': 'Divergência Baixista',
            'ESCORA_DETECTADA': 'Escora Detectada',
            'PRESSAO_COMPRA': 'Pressão Compradora',
            'PRESSAO_VENDA': 'Pressão Vendedora',
            'ABSORPTION_DETECTED': 'Absorção Detectada',
            'EXHAUSTION_DETECTED': 'Exaustão Detectada'
        }
        
        # Tenta formatar ou usa o padrão com espaços
        return format_map.get(pattern.upper(), pattern.replace('_', ' ').title())

    # Métodos de acesso público
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
            'tolerancia_proximidade': self.tolerancia_proximidade,
            'niveis': {
                nome: {
                    'preco': nivel.price,
                    'tipo': nivel.type,
                    'forca': nivel.strength
                }
                for nome, nivel in self.niveis_calculados.items()
            }
        }
