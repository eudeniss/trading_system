# application/services/calculated_market/ptax_fetcher.py
"""
Módulo responsável exclusivamente por buscar a PTAX do BCB.
"""
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class PtaxFetcher:
    """Classe responsável exclusivamente por buscar a PTAX do BCB."""

    def __init__(self, config: dict):
        """
        Inicializa o fetcher com configurações.
        
        Args:
            config: Dicionário de configuração com parâmetros da API
        """
        self.api_config = config.get('ptax_api', {})
        self.timeout = self.api_config.get('timeout', 10)
        self.default_ptax = self.api_config.get('default_ptax', 5.4500)
        
        # URLs da API do BCB
        self.live_url = self.api_config.get(
            'live_url', 
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados/ultimos/5?formato=json"
        )
        self.historical_url_template = self.api_config.get(
            'historical_url_template',
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados?formato=json&dataInicial={start}&dataFinal={end}"
        )

    def fetch_ptax(self, target_date: Optional[datetime] = None) -> Optional[float]:
        """
        Busca a PTAX de referência.
        
        Args:
            target_date: Data alvo para busca histórica (None = PTAX mais recente)
            
        Returns:
            Valor da PTAX ou None em caso de erro
        """
        try:
            if target_date:
                logger.info(f"🔄 Buscando PTAX histórica para {target_date.strftime('%d/%m/%Y')}")
                return self._fetch_historical_ptax(target_date)
            else:
                logger.info("🔄 Buscando PTAX mais recente")
                return self._fetch_latest_ptax()
        except Exception as e:
            logger.error(f"Erro geral ao buscar PTAX: {e}")
            return self._get_fallback_ptax()

    def _fetch_historical_ptax(self, target_date: datetime) -> Optional[float]:
        """
        Busca PTAX histórica, procurando até 10 dias úteis anteriores.
        
        Args:
            target_date: Data alvo
            
        Returns:
            PTAX do dia útil mais próximo ou fallback
        """
        # Tenta buscar por até 10 dias para trás para encontrar um dia útil
        for days_back in range(1, 11):
            query_date = target_date - timedelta(days=days_back)
            ptax = self._fetch_for_specific_date(query_date)
            if ptax is not None:
                logger.info(f"✅ PTAX histórica encontrada: {ptax:.4f} ({query_date.strftime('%d/%m/%Y')})")
                return ptax
        
        logger.warning("⚠️ Não foi possível encontrar PTAX histórica nos últimos 10 dias")
        return self._get_fallback_ptax()

    def _fetch_for_specific_date(self, date: datetime) -> Optional[float]:
        """
        Busca PTAX para uma data específica.
        
        Args:
            date: Data para buscar
            
        Returns:
            PTAX da data ou None se não disponível
        """
        date_str = date.strftime('%d/%m/%Y')
        url = self.historical_url_template.format(start=date_str, end=date_str)
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            if data and isinstance(data, list) and len(data) > 0:
                ptax = float(data[0]['valor'])
                logger.debug(f"PTAX obtida para {date_str}: {ptax:.4f}")
                return ptax
                
        except requests.RequestException as e:
            logger.debug(f"Erro de rede ao buscar PTAX de {date_str}: {e}")
        except (ValueError, KeyError, IndexError) as e:
            logger.debug(f"Erro ao processar dados da PTAX de {date_str}: {e}")
        
        return None

    def _fetch_latest_ptax(self) -> Optional[float]:
        """
        Busca a PTAX mais recente disponível.
        
        Returns:
            PTAX mais recente ou fallback
        """
        try:
            response = requests.get(self.live_url, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            if data and isinstance(data, list) and len(data) > 0:
                # Pega o valor mais recente (último da lista)
                ptax = float(data[-1]['valor'])
                logger.info(f"💱 PTAX atual obtida: {ptax:.4f}")
                return ptax
                
        except requests.RequestException as e:
            logger.error(f"Erro de rede ao buscar PTAX atual: {e}")
        except (ValueError, KeyError, IndexError) as e:
            logger.error(f"Erro ao processar resposta da PTAX: {e}")
        
        return self._get_fallback_ptax()

    def _get_fallback_ptax(self) -> float:
        """
        Retorna valor padrão de PTAX quando API falha.
        
        Returns:
            Valor padrão configurado
        """
        logger.warning(f"⚠️ Usando PTAX padrão de fallback: {self.default_ptax}")
        return self.default_ptax