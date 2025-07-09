# application/services/calculated_market/level_calculator.py
"""
Módulo responsável pelos cálculos matemáticos dos níveis de mercado.
"""
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class CalculatedLevel:
    """Representa um nível calculado do mercado."""
    name: str
    price: float
    type: str  # 'RESISTENCIA', 'SUPORTE', 'PIVOT'
    strength: int  # 0-3
    distance: Optional[float] = None
    position: Optional[str] = None  # 'ACIMA', 'ABAIXO'


class LevelCalculator:
    """Classe responsável apenas pelos cálculos matemáticos dos níveis."""

    def __init__(self, config: dict):
        """
        Inicializa a calculadora com parâmetros.
        
        Args:
            config: Configurações dos cálculos
        """
        self.cupom_cambial = config.get('cupom_cambial', 25)
        self.volatilidade_unidade = config.get('volatilidade_unidade', 12.5)
        
        # Multiplicadores dos níveis (do roadmap)
        self.multiplicadores = config.get('multiplicadores', {
            'SOFRER_2X': 1.60,
            'SOFRER': 1.25,
            'SX_SUP': 0.80,
            'DEFENDO': 0.45,
            'BASE': 0.00,    # PIVOT = BASE = Valor Justo
            'PB': -0.45,     # Primeiro suporte
            'SX': -0.80,
            'DEVENDO': -1.25,
            'SOFGRE': -1.60
        })

    def calculate(self, ptax: float) -> Tuple[float, Dict[str, CalculatedLevel]]:
        """
        Calcula o valor justo e todos os níveis baseados na PTAX.
        
        Args:
            ptax: Valor da PTAX
            
        Returns:
            Tupla (valor_justo, dicionário_de_níveis)
        """
        if not ptax or ptax <= 0:
            return 0.0, {}
        
        # Calcula valor justo (fórmula do roadmap)
        valor_justo = (ptax * 1000) + self.cupom_cambial
        
        # Calcula cada nível
        niveis_calculados = {}
        
        for nome, multiplicador in self.multiplicadores.items():
            # Fórmula: Valor Justo + (Multiplicador * Volatilidade)
            preco = valor_justo + (multiplicador * self.volatilidade_unidade)
            
            # Determina tipo do nível baseado no multiplicador
            if multiplicador > 0:
                tipo = 'RESISTENCIA'
            elif multiplicador < 0:
                tipo = 'SUPORTE'
            else:
                tipo = 'PIVOT'
            
            # Calcula força do nível (0-3)
            strength = min(abs(int(multiplicador * 2)), 3)
            
            niveis_calculados[nome] = CalculatedLevel(
                name=nome,
                price=round(preco, 2),
                type=tipo,
                strength=strength
            )
        
        return round(valor_justo, 2), niveis_calculados

    def calculate_stops_and_targets(self, action: str, current_price: float, 
                                  niveis: Dict[str, CalculatedLevel]) -> Tuple[float, float]:
        """
        Calcula stop loss e target baseado na ação e níveis disponíveis.
        
        Args:
            action: 'COMPRA' ou 'VENDA'
            current_price: Preço atual
            niveis: Dicionário de níveis calculados
            
        Returns:
            Tupla (stop_loss, target)
        """
        if action == 'COMPRA':
            # Stop: próximo suporte abaixo - margem
            supports = [n.price for n in niveis.values() 
                       if n.type == 'SUPORTE' and n.price < current_price]
            stop = max(supports) - 5.0 if supports else current_price - 20.0
            
            # Target: próxima resistência acima
            resistances = [n.price for n in niveis.values() 
                          if n.type == 'RESISTENCIA' and n.price > current_price]
            target = min(resistances) if resistances else current_price + 20.0
            
        else:  # VENDA
            # Stop: próxima resistência acima + margem
            resistances = [n.price for n in niveis.values() 
                          if n.type == 'RESISTENCIA' and n.price > current_price]
            stop = min(resistances) + 5.0 if resistances else current_price + 20.0
            
            # Target: próximo suporte abaixo
            supports = [n.price for n in niveis.values() 
                       if n.type == 'SUPORTE' and n.price < current_price]
            target = max(supports) if supports else current_price - 20.0
        
        return round(stop, 2), round(target, 2)