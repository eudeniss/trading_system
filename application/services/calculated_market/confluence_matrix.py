# application/services/calculated_market/confluence_matrix.py
"""
Módulo que armazena e gerencia as regras de confluência.
"""
from typing import Optional, Dict, Tuple


class ConfluenceMatrix:
    """Armazena e fornece acesso às regras de confluência entre padrões e níveis."""

    def __init__(self, config: dict):
        """
        Inicializa a matriz com as regras de confluência.
        
        Args:
            config: Configurações contendo a matriz
        """
        # Se houver regras no config, usa elas. Senão, usa as padrões
        self.rules = config.get('matriz_confluencia', self._get_default_rules())
        
        # Regras especiais para força extrema
        self.extreme_force_threshold = config.get('extreme_force_threshold', 9)
        self.minimum_force = config.get('minimum_force', 7)
        self.minimum_confidence = config.get('minimum_confidence', 0.65)

    def _get_default_rules(self) -> Dict[Tuple[str, str], Dict]:
        """Retorna as regras padrão de confluência do roadmap."""
        return {
            # 🟢 SINAIS DE COMPRA
            ('ABSORCAO_COMPRADORA', 'DEVENDO'): {
                'acao': 'COMPRA', 'confianca': 0.85, 'desc': 'Absorção em suporte forte'
            },
            ('ABSORCAO_COMPRADORA', 'SOFGRE'): {
                'acao': 'COMPRA', 'confianca': 0.90, 'desc': 'Absorção em suporte extremo'
            },
            ('ABSORCAO_COMPRADORA', 'PB'): {
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
            
            # NOVOS PADRÕES DE COMPRA
            ('DIVERGENCIA_ALTA', 'DEVENDO'): {
                'acao': 'COMPRA', 'confianca': 0.85, 'desc': 'Divergência altista em suporte forte'
            },
            ('DIVERGENCIA_ALTA', 'SOFGRE'): {
                'acao': 'COMPRA', 'confianca': 0.90, 'desc': 'Divergência altista em suporte extremo'
            },
            ('DIVERGENCIA_ALTA', 'PB'): {
                'acao': 'COMPRA', 'confianca': 0.75, 'desc': 'Divergência altista em suporte primário'
            },
            ('MOMENTUM_EXTREMO', 'SOFGRE'): {  # Momentum de COMPRA em suporte extremo
                'acao': 'COMPRA', 'confianca': 0.85, 'desc': 'Momentum de compra extremo em suporte máximo'
            },
            ('MOMENTUM_EXTREMO', 'DEVENDO'): {  # Momentum de COMPRA em suporte forte
                'acao': 'COMPRA', 'confianca': 0.80, 'desc': 'Momentum de compra em suporte forte'
            },
            
            # 🔴 SINAIS DE VENDA
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
            },
            
            # NOVOS PADRÕES DE VENDA
            ('DIVERGENCIA_BAIXA', 'SOFRER'): {
                'acao': 'VENDA', 'confianca': 0.85, 'desc': 'Divergência baixista em resistência forte'
            },
            ('DIVERGENCIA_BAIXA', 'SOFRER_2X'): {
                'acao': 'VENDA', 'confianca': 0.90, 'desc': 'Divergência baixista em resistência extrema'
            },
            ('DIVERGENCIA_BAIXA', 'DEFENDO'): {
                'acao': 'VENDA', 'confianca': 0.75, 'desc': 'Divergência baixista em resistência primária'
            },
            ('MOMENTUM_EXTREMO', 'SOFRER_2X'): {  # Momentum de VENDA em resistência extrema
                'acao': 'VENDA', 'confianca': 0.85, 'desc': 'Momentum de venda extremo em resistência máxima'
            },
            ('MOMENTUM_EXTREMO', 'SOFRER'): {  # Momentum de VENDA em resistência forte
                'acao': 'VENDA', 'confianca': 0.80, 'desc': 'Momentum de venda em resistência forte'
            }
        }

    def find_rule(self, pattern_name: str, level_name: str, 
                  signal_direction: Optional[str] = None) -> Optional[Dict]:
        """
        Encontra uma regra na matriz de confluência.
        
        Args:
            pattern_name: Nome do padrão (ex: 'MOMENTUM_EXTREMO')
            level_name: Nome do nível (ex: 'SOFRER')
            signal_direction: Direção do sinal quando aplicável ('COMPRA' ou 'VENDA')
            
        Returns:
            Regra encontrada ou None
        """
        # Busca básica pela tupla (padrão, nível)
        rule = self.rules.get((pattern_name, level_name))
        
        # Se encontrou regra e há direção no sinal, valida
        if rule and signal_direction:
            rule_action = rule.get('acao', '').upper()
            signal_dir_upper = signal_direction.upper()
            
            # A regra só é válida se as direções batem
            if rule_action != signal_dir_upper:
                return None
        
        return rule

    def check_extreme_conditions(self, strength: int, level_name: str) -> Optional[Dict]:
        """
        Verifica condições especiais para força extrema.
        
        Args:
            strength: Força do sinal (0-10)
            level_name: Nome do nível
            
        Returns:
            Regra especial se aplicável
        """
        # Força ≥9 + Nível Extremo sempre gera sinal
        if strength >= self.extreme_force_threshold:
            if level_name == 'SOFRER_2X':
                return {
                    'acao': 'VENDA',
                    'confianca': 0.85,
                    'desc': 'Força extrema em resistência máxima'
                }
            elif level_name == 'SOFGRE':
                return {
                    'acao': 'COMPRA',
                    'confianca': 0.85,
                    'desc': 'Força extrema em suporte máximo'
                }
        
        return None

    def is_valid_signal(self, rule: Dict, strength: int) -> bool:
        """
        Valida se um sinal atende aos critérios mínimos.
        
        Args:
            rule: Regra da matriz
            strength: Força do sinal
            
        Returns:
            True se válido
        """
        if not rule:
            return False
            
        # Verifica força mínima
        if strength < self.minimum_force:
            return False
            
        # Verifica confiança mínima
        confidence = rule.get('confianca', 0)
        if confidence < self.minimum_confidence:
            return False
            
        return True