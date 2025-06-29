# analyzers/formatters/signal_formatter.py
from typing import Dict
from domain.entities.signal import Signal, SignalSource, SignalLevel

class SignalFormatter:
    """Formata os dicionários brutos dos detectores em entidades Signal."""

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
            else:
                return f"🛡️ {direction} | {escora_type} {symbol} @ {level:.2f} (Vol: {vol}, {conc:.0f}%)"
        
        if pattern == "PACE_ANOMALY":
            pace = details.get('pace', 0.0)
            baseline = details.get('baseline', 0.0)
            direction = details.get('direction', 'BATALHA')
            return f"⚡ {direction} | Pace anormal {symbol}: {pace:.1f} t/s (normal: {baseline:.1f})"

        if pattern == "DIVERGENCIA_BAIXA":
            roc = details.get('cvd_roc', 0.0)
            return f"📉 VENDA | Divergência Baixista {symbol}: Preço sobe, fluxo cai (ROC: {roc:.0f}%)"

        if pattern == "DIVERGENCIA_ALTA":
            roc = details.get('cvd_roc', 0.0)
            return f"📈 COMPRA | Divergência Altista {symbol}: Preço cai, fluxo sobe (ROC: {roc:.0f}%)"
            
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

        return f"Sinal de Tape Reading: {pattern} em {symbol}"

    def _get_signal_level(self, pattern: str) -> SignalLevel:
        """Define o nível de alerta do sinal."""
        high_priority = [
            "ESCORA_DETECTADA", "DIVERGENCIA_BAIXA", "DIVERGENCIA_ALTA",
            "MOMENTUM_EXTREMO", "ICEBERG", "PRESSAO_COMPRA", "PRESSAO_VENDA"
        ]
        medium_priority = ["PACE_ANOMALY", "VOLUME_SPIKE"]

        if pattern in high_priority:
            return SignalLevel.ALERT
        if pattern in medium_priority:
            return SignalLevel.WARNING
            
        return SignalLevel.INFO