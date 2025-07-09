#core/formatters/signal_formatter.py
"""Formatador de sinais otimizado - FASE 5 COM NOVOS PADRÕES."""
from typing import Dict
from core.entities.signal import Signal, SignalSource, SignalLevel


class SignalFormatter:
    """Formata os dicionários brutos dos detectores em entidades Signal estruturadas."""
    
    __slots__ = []  # Sem estado = mais eficiente

    def format(self, raw_signal: Dict, symbol: str) -> Signal:
        """Converte um dicionário de sinal em uma entidade Signal estruturada."""
        pattern = raw_signal.get("pattern", "UNKNOWN")
        message = self._create_message(pattern, symbol, raw_signal)
        level = self._get_signal_level(pattern)

        # Adiciona o padrão original aos detalhes para rastreabilidade
        raw_signal['original_pattern'] = pattern

        return Signal(
            source=SignalSource.TAPE_READING,
            level=level,
            message=message,
            details={"symbol": symbol, **raw_signal}
        )

    def _create_message(self, pattern: str, symbol: str, details: Dict) -> str:
        """Cria uma mensagem clara e concisa para o sinal."""
        if pattern == "ESCORA_DETECTADA":
            level = details.get('level', 0.0)
            vol = details.get('volume', 0)
            conc = details.get('concentration', 0.0) * 100
            direction = details.get('direction', 'COMPRA')
            escora_type = details.get('type', 'SUPORTE')
            
            if escora_type == "ABSORÇÃO":
                if direction == "COMPRA":
                    return f"🛡️ ABSORÇÃO COMPRADORA {symbol} @ {level:.2f} | Vendedores absorvidos (Vol: {vol}, {conc:.0f}%)"
                else:
                    return f"🛡️ ABSORÇÃO VENDEDORA {symbol} @ {level:.2f} | Compradores absorvidos (Vol: {vol}, {conc:.0f}%)"
            elif escora_type == "EXHAUSTION":
                return f"🔥 EXHAUSTION {symbol} @ {level:.2f} | Volume extremo de {direction} (Vol: {vol}, {conc:.0f}%)"
            else:
                return f"🛡️ {direction} | {escora_type} {symbol} @ {level:.2f} (Vol: {vol}, {conc:.0f}%)"
        
        if pattern == "PACE_ANOMALY":
            pace = details.get('pace', 0.0)
            baseline = details.get('baseline', 0.0)
            direction = details.get('direction', 'BATALHA')
            return f"⚡ {direction} | Pace anormal {symbol}: {pace:.1f} t/s (normal: {baseline:.1f})"

        if pattern == "DIVERGENCIA_BAIXA":
            roc = details.get('cvd_roc', 0.0)
            price_dir = details.get('price_direction', 'SUBINDO')
            flow_dir = details.get('flow_direction', 'CAINDO')
            return f"📉 VENDA | Divergência Baixista {symbol}: Preço {price_dir} ↑ MAS Fluxo {flow_dir} ↓ (ROC: {roc:.0f}%) = FRAQUEZA!"

        if pattern == "DIVERGENCIA_ALTA":
            roc = details.get('cvd_roc', 0.0)
            price_dir = details.get('price_direction', 'CAINDO')
            flow_dir = details.get('flow_direction', 'SUBINDO')
            return f"📈 COMPRA | Divergência Altista {symbol}: Preço {price_dir} ↓ MAS Fluxo {flow_dir} ↑ (ROC: {roc:.0f}%) = FORÇA OCULTA!"
            
        if pattern == "MOMENTUM_EXTREMO":
            roc = details.get('cvd_roc', 0.0)
            direction = details.get('direction', 'NEUTRO')
            return f"🚀 {direction} | Momentum extremo {symbol} (CVD ROC: {roc:+.0f}%)"
            
        if pattern == "ICEBERG":
            price = details.get('price', 0.0)
            reps = details.get('repetitions', 0)
            unit_vol = details.get('unit_volume', 0)
            position = details.get('position', 'TRAVAMENTO')
            total = details.get('total_volume', 0)
            return f"🧊 ICEBERG {symbol} @ {price:.2f} | {position} ({reps}x{unit_vol} = {total} total)"
        
        if pattern == "PRESSAO_COMPRA":
            ratio = details.get('ratio', 0.0) * 100
            total = details.get('total_volume', 0)
            return f"💹 COMPRA | Pressão compradora {symbol}: {ratio:.0f}% do volume (Total: {total})"
        
        if pattern == "PRESSAO_VENDA":
            ratio = details.get('ratio', 0.0) * 100
            total = details.get('total_volume', 0)
            return f"💥 VENDA | Pressão vendedora {symbol}: {ratio:.0f}% do volume (Total: {total})"
        
        if pattern == "VOLUME_SPIKE":
            mult = details.get('multiplier', 0.0)
            direction = details.get('direction', 'NEUTRO')
            current = details.get('current_volume', 0)
            return f"📊 {direction} | Spike de volume {symbol}: {mult:.1f}x normal (Vol: {current})"
        
        # ═══════════════════════════════════════════════════════════════
        # FASE 4.2 - DINÂMICA DO BOOK
        # ═══════════════════════════════════════════════════════════════
        
        if pattern == "BOOK_PULLING":
            side = details.get('side', 'UNKNOWN')
            price = details.get('price', 0.0)
            reduction = details.get('reduction_pct', 0)
            return f"🎣 PULLING {symbol} | Liquidez removida no {side} @ {price:.2f} ({reduction:.0f}% redução)"
        
        if pattern == "BOOK_STACKING":
            side = details.get('side', 'UNKNOWN')
            price = details.get('price', 0.0)
            increase = details.get('increase_ratio', 0)
            return f"📚 STACKING {symbol} | Liquidez adicionada no {side} @ {price:.2f} ({increase:.1f}x)"
        
        if pattern == "FLASH_ORDER":
            side = details.get('side', 'UNKNOWN')
            price = details.get('price', 0.0)
            volume = details.get('volume', 0)
            lifetime = details.get('lifetime_seconds', 0)
            return f"⚡ FLASH ORDER {symbol} | {side} {volume} @ {price:.2f} sumiu em {lifetime:.1f}s"
        
        if pattern == "IMBALANCE_SHIFT":
            direction = details.get('direction', 'UNKNOWN')
            desc = details.get('description', '')
            return f"⚖️ IMBALANCE {symbol} | {desc}"
        
        # ═══════════════════════════════════════════════════════════════
        # FASE 5 - NOVOS DETECTORES ESPECIALIZADOS
        # ═══════════════════════════════════════════════════════════════
        
        if pattern == "INSTITUTIONAL_FOOTPRINT":
            confidence = details.get('confidence', 0) * 100
            operation = details.get('operation_type', 'UNKNOWN')
            volume = details.get('details', {}).get('total_volume', 0)
            style = details.get('characteristics', {}).get('execution_style', '')
            
            operation_map = {
                "ACCUMULATION_AGGRESSIVE": "🏦 Acumulação Agressiva",
                "ACCUMULATION_PATIENT": "🏦 Acumulação Paciente",
                "DISTRIBUTION_AGGRESSIVE": "🏦 Distribuição Agressiva",
                "DISTRIBUTION_PATIENT": "🏦 Distribuição Paciente",
                "POSITION_MAINTENANCE": "🏦 Manutenção de Posição",
                "MARKET_MAKING": "🏦 Market Making"
            }
            
            op_desc = operation_map.get(operation, operation)
            return f"{op_desc} {symbol} | Pegada institucional detectada ({confidence:.0f}% certeza, Vol: {volume:,})"
        
        if pattern == "HIDDEN_LIQUIDITY":
            confidence = details.get('confidence', 0) * 100
            total_hidden = details.get('estimated_hidden_volume', 0)
            levels = details.get('hidden_levels', [])
            methods = details.get('detection_methods', [])
            
            level_info = ""
            if levels:
                top_level = levels[0]
                level_info = f" @ {top_level['price']:.2f}"
            
            return f"🌊 LIQUIDEZ OCULTA {symbol}{level_info} | ~{total_hidden:.0f} contratos invisíveis ({confidence:.0f}% conf)"
        
        if pattern == "MULTIFRAME_DIVERGENCE":
            div_type = details.get('divergence_type', '')
            desc = details.get('description', '')
            confidence = details.get('confidence', 0) * 100
            
            emoji_map = {
                "BULLISH_DIVERGENCE": "🔄📈",
                "BEARISH_DIVERGENCE": "🔄📉",
                "SHORT_TERM_REVERSAL": "🔄⚡"
            }
            
            emoji = emoji_map.get(div_type, "🔄")
            return f"{emoji} DIVERGÊNCIA MULTIFRAME {symbol} | {desc} ({confidence:.0f}% conf)"
        
        if pattern == "MULTIFRAME_CONFLUENCE":
            direction = details.get('direction', '')
            strength = details.get('strength', 0) * 100
            aligned = details.get('timeframes_aligned', 0)
            
            emoji = "🔥📈" if direction == "COMPRA" else "🔥📉"
            return f"{emoji} CONFLUÊNCIA {symbol} | {direction} confirmada em {aligned} timeframes ({strength:.0f}% força)"
        
        if pattern == "REGIME_CHANGE":
            old_regime = details.get('previous_regime', '')
            new_regime = details.get('new_regime', '')
            
            regime_emoji = {
                "ACCUMULATION": "📈",
                "DISTRIBUTION": "📉",
                "BALANCED": "⚖️",
                "TRANSITIONING": "🔄"
            }
            
            old_emoji = regime_emoji.get(old_regime, "")
            new_emoji = regime_emoji.get(new_regime, "")
            
            return f"🎭 MUDANÇA DE REGIME {symbol} | {old_regime}{old_emoji} → {new_regime}{new_emoji}"
        
        if pattern == "HIDDEN_ACCUMULATION":
            price_change = details.get('price_change', 0)
            net_flow = details.get('net_flow', 0) * 100
            return f"🤫📈 ACUMULAÇÃO OCULTA {symbol} | Preço cai {price_change:.1f}% mas fluxo comprador {net_flow:.0f}%"
        
        if pattern == "HIDDEN_DISTRIBUTION":
            price_change = details.get('price_change', 0)
            net_flow = details.get('net_flow', 0) * 100
            return f"🤫📉 DISTRIBUIÇÃO OCULTA {symbol} | Preço sobe {price_change:.1f}% mas fluxo vendedor {net_flow:.0f}%"
        
        if pattern == "TRAP_DETECTED":
            trap_type = details.get('trap_type', '')
            desc = details.get('description', '')
            confidence = details.get('confidence', 0) * 100
            
            trap_emoji = {
                "BULL_TRAP": "🪤🐂",
                "BEAR_TRAP": "🪤🐻",
                "LIQUIDITY_TRAP": "🪤💧",
                "STOP_HUNT": "🪤🎯",
                "SQUEEZE_TRAP": "🪤💥"
            }
            
            emoji = trap_emoji.get(trap_type, "🪤")
            return f"{emoji} ARMADILHA {symbol} | {desc} ({confidence:.0f}% conf)"

        return f"Sinal de Tape Reading: {pattern} em {symbol}"

    def _get_signal_level(self, pattern: str) -> SignalLevel:
        """Define o nível de alerta do sinal."""
        high_priority = [
            "ESCORA_DETECTADA", "DIVERGENCIA_BAIXA", "DIVERGENCIA_ALTA",
            "MOMENTUM_EXTREMO", "ICEBERG", "PRESSAO_COMPRA", "PRESSAO_VENDA",
            # FASE 5
            "INSTITUTIONAL_FOOTPRINT", "HIDDEN_LIQUIDITY", 
            "MULTIFRAME_DIVERGENCE", "MULTIFRAME_CONFLUENCE",
            "HIDDEN_ACCUMULATION", "HIDDEN_DISTRIBUTION",
            "TRAP_DETECTED"
        ]
        medium_priority = [
            "PACE_ANOMALY", "VOLUME_SPIKE",
            # FASE 4.2
            "BOOK_PULLING", "BOOK_STACKING", "FLASH_ORDER",
            # FASE 5
            "REGIME_CHANGE", "IMBALANCE_SHIFT"
        ]

        if pattern in high_priority:
            return SignalLevel.ALERT
        if pattern in medium_priority:
            return SignalLevel.WARNING
            
        return SignalLevel.INFO