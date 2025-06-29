# application/services/confluence_service.py
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta

from domain.entities.signal import Signal, SignalSource, SignalLevel
from config import settings

class ConfluenceService:
    """
    Serviço que analisa a confluência entre sinais de arbitragem e de tape reading
    para gerar sinais de alta confiança.
    """

    def __init__(self):
        self.config = settings.TAPE_READING_CONFIG
        self.cvd_threshold = self.config.get('cvd_threshold', 50)
        self.last_confluence_time = None
        self.cooldown = timedelta(seconds=settings.ARBITRAGE_CONFIG.get('signal_cooldown', 10))

    def analyze(self, arbitrage_opp: Dict, tape_summaries: Dict) -> Optional[Signal]:
        """
        Analisa a confluência e retorna um Signal se a oportunidade for confirmada.
        """
        is_confirmed, reason, confidence = self._check_confirmation(arbitrage_opp, tape_summaries)

        if not is_confirmed:
            return None

        # Cooldown check
        now = datetime.now()
        if self.last_confluence_time and (now - self.last_confluence_time) < self.cooldown:
            return None
        
        self.last_confluence_time = now

        action = "VENDA" if "VENDER DOL" in arbitrage_opp['action'] else "COMPRA"
        profit = arbitrage_opp['profit']
        spread = arbitrage_opp['spread']

        message = f"🔥 {action} CONFIRMADA | Spread: {spread:.1f}pts (R${profit:.0f}) | {reason} [{confidence}]"

        details = {
            "arbitrage_opportunity": arbitrage_opp,
            "tape_summaries": tape_summaries,
            "confirmation_reason": reason,
            "confidence_level": confidence
        }

        return Signal(
            source=SignalSource.CONFLUENCE,
            level=SignalLevel.ALERT,
            message=message,
            details=details
        )
        
    def _check_confirmation(self, arb_opp: Dict, tape_summaries: Dict) -> Tuple[bool, str, str]:
        """Lógica interna para verificar a confirmação do sinal."""
        dol_summary = tape_summaries.get('DOL', {})
        wdo_summary = tape_summaries.get('WDO', {})

        dol_cvd = dol_summary.get('cvd', 0)
        wdo_cvd = wdo_summary.get('cvd', 0)

        action = arb_opp['action']

        # Vender DOL (espera-se fluxo vendedor no DOL ou comprador no WDO)
        if 'VENDER DOL' in action:
            # Cenário ideal: fluxo em ambos os ativos
            if dol_cvd < -self.cvd_threshold and wdo_cvd > self.cvd_threshold:
                return True, "Fluxo Vendedor DOL + Comprador WDO", "MUITO ALTA"
            # Confirmação apenas no DOL
            if dol_cvd < -self.cvd_threshold / 2:
                confidence = "ALTA" if dol_cvd < -self.cvd_threshold else "MÉDIA"
                return True, f"Fluxo Vendedor DOL (CVD: {dol_cvd})", confidence
            # Confirmação apenas no WDO
            if wdo_cvd > self.cvd_threshold / 2:
                confidence = "ALTA" if wdo_cvd > self.cvd_threshold else "MÉDIA"
                return True, f"Fluxo Comprador WDO (CVD: {wdo_cvd})", confidence

        # Comprar DOL (espera-se fluxo comprador no DOL ou vendedor no WDO)
        elif 'COMPRAR DOL' in action:
            if dol_cvd > self.cvd_threshold and wdo_cvd < -self.cvd_threshold:
                return True, "Fluxo Comprador DOL + Vendedor WDO", "MUITO ALTA"
            if dol_cvd > self.cvd_threshold / 2:
                confidence = "ALTA" if dol_cvd > self.cvd_threshold else "MÉDIA"
                return True, f"Fluxo Comprador DOL (CVD: {dol_cvd})", confidence
            if wdo_cvd < -self.cvd_threshold / 2:
                confidence = "ALTA" if wdo_cvd < -self.cvd_threshold else "MÉDIA"
                return True, f"Fluxo Vendedor WDO (CVD: {wdo_cvd})", confidence
                
        return False, "Sem confirmação de fluxo", "BAIXA"