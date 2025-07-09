# config/settings.py
"""
Carregador de configurações - SEM VALIDAÇÃO DE ARBITRAGE
"""
import os
import re
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from datetime import datetime
from functools import lru_cache

# Tenta importar python-dotenv se disponível
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Exceção para erros de configuração."""
    pass


class ConfigValidator:
    """Valida configurações do sistema."""
    
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> List[str]:
        """
        Valida a configuração e retorna lista de erros.
        
        Returns:
            Lista de mensagens de erro (vazia se tudo OK)
        """
        errors = []
        
        # Validações obrigatórias (REMOVIDO 'arbitrage')
        required_sections = ['system', 'excel', 'wdo', 'dol', 'tape_reading', 'risk_management']
        
        for section in required_sections:
            if section not in config:
                errors.append(f"Seção obrigatória ausente: {section}")
        
        # Valida Excel
        if 'excel' in config:
            if 'file' not in config['excel']:
                errors.append("excel.file é obrigatório")
            else:
                # Verifica se o arquivo existe (se não for template)
                excel_file = config['excel']['file']
                if not excel_file.startswith('${') and not Path(excel_file).exists():
                    errors.append(f"Arquivo Excel não encontrado: {excel_file}")
        
        # Valida limites numéricos
        if 'risk_management' in config:
            rm = config['risk_management']
            
            # Verifica limites de sinais
            if 'signal_limits' in rm:
                limits = rm['signal_limits']
                if limits.get('max_per_minute', 0) > 100:
                    errors.append("max_per_minute muito alto (>100)")
                if limits.get('max_concurrent', 0) > 20:
                    errors.append("max_concurrent muito alto (>20)")
            
            # Verifica limites financeiros
            if 'financial_limits' in rm:
                fin = rm['financial_limits']
                if fin.get('max_drawdown_pct', 0) > 10:
                    errors.append("max_drawdown_pct muito alto (>10%)")
        
        # Valida tape reading
        if 'tape_reading' in config:
            tr = config['tape_reading']
            if tr.get('buffer_size', 0) > 100000:
                errors.append("buffer_size muito grande (>100k)")
            
            # Valida cooldowns
            if 'pattern_cooldown' in tr:
                for pattern, cooldown in tr['pattern_cooldown'].items():
                    if cooldown < 5:
                        errors.append(f"Cooldown muito baixo para {pattern}: {cooldown}s")
        
        return errors
    
    @staticmethod
    def validate_types(config: Dict[str, Any]) -> List[str]:
        """Valida tipos de dados."""
        errors = []
        
        # Define tipos esperados (REMOVIDO arbitrage.min_profit)
        type_specs = {
            'system.update_interval': (float, int),
            'tape_reading.buffer_size': int,
            'risk_management.signal_quality_threshold': float,
        }
        
        for path, expected_types in type_specs.items():
            value = ConfigValidator._get_nested_value(config, path)
            if value is not None:
                if not isinstance(value, expected_types):
                    errors.append(
                        f"{path} deve ser {expected_types}, mas é {type(value)}"
                    )
        
        return errors
    
    @staticmethod
    def _get_nested_value(config: Dict, path: str) -> Any:
        """Obtém valor aninhado do config."""
        keys = path.split('.')
        value = config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return value


class ConfigLoader:
    """Carregador principal de configurações."""
    
    # Padrão para variáveis de ambiente: ${VAR_NAME:default_value}
    ENV_VAR_PATTERN = re.compile(r'\$\{([^:}]+)(?::([^}]+))?\}')
    
    def __init__(self, config_path: str = "config/config.yaml", 
                 env_file: str = ".env"):
        """
        Inicializa o carregador de configurações.
        
        Args:
            config_path: Caminho do arquivo YAML
            env_file: Caminho do arquivo .env (opcional)
        """
        self.config_path = Path(config_path)
        self.env_file = Path(env_file)
        self._config_cache = None
        self._last_modified = None
        
        # Carrega variáveis de ambiente do arquivo .env se disponível
        if HAS_DOTENV and self.env_file.exists():
            load_dotenv(self.env_file)
            logger.info(f"Variáveis de ambiente carregadas de {self.env_file}")
    
    def load(self, validate: bool = True) -> Dict[str, Any]:
        """
        Carrega configurações com cache e validação.
        
        Args:
            validate: Se deve validar a configuração
            
        Returns:
            Dicionário de configuração
            
        Raises:
            ConfigurationError: Se houver erro na configuração
        """
        # Verifica cache
        if self._is_cache_valid():
            return self._config_cache
        
        # Carrega configuração
        config = self._load_yaml()
        
        # Substitui variáveis de ambiente
        config = self._substitute_env_vars(config)
        
        # Merge com defaults
        config = self._merge_with_defaults(config)
        
        # Valida se solicitado
        if validate:
            self._validate_config(config)
        
        # Atualiza cache
        self._config_cache = config
        self._last_modified = self.config_path.stat().st_mtime
        
        logger.info("Configuração carregada com sucesso")
        return config
    
    def _is_cache_valid(self) -> bool:
        """Verifica se o cache ainda é válido."""
        if self._config_cache is None or self._last_modified is None:
            return False
        
        if not self.config_path.exists():
            return False
        
        current_mtime = self.config_path.stat().st_mtime
        return current_mtime == self._last_modified
    
    def _load_yaml(self) -> Dict[str, Any]:
        """Carrega arquivo YAML."""
        if not self.config_path.exists():
            raise ConfigurationError(
                f"Arquivo de configuração não encontrado: {self.config_path}"
            )
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not isinstance(config, dict):
                raise ConfigurationError("Configuração deve ser um dicionário")
            
            return config
            
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Erro ao parsear YAML: {e}")
        except Exception as e:
            raise ConfigurationError(f"Erro ao carregar configuração: {e}")
    
    def _substitute_env_vars(self, obj: Any) -> Any:
        """
        Substitui variáveis de ambiente recursivamente.
        Formato: ${VAR_NAME:default_value}
        """
        if isinstance(obj, str):
            # Procura por padrões de variável
            def replacer(match):
                var_name = match.group(1)
                default_value = match.group(2)
                
                # Obtém valor da variável de ambiente
                value = os.environ.get(var_name, default_value)
                
                # Converte tipos básicos
                if value is not None:
                    # Booleanos
                    if value.lower() in ('true', 'false'):
                        return value.lower() == 'true'
                    # Números
                    try:
                        if '.' in value:
                            return float(value)
                        else:
                            return int(value)
                    except ValueError:
                        pass
                
                return value
            
            # Se a string inteira é uma variável, retorna o valor convertido
            if obj.startswith('${') and obj.endswith('}'):
                result = self.ENV_VAR_PATTERN.sub(replacer, obj)
                return result
            
            # Caso contrário, faz substituição parcial mantendo string
            return self.ENV_VAR_PATTERN.sub(lambda m: str(replacer(m)), obj)
        
        elif isinstance(obj, dict):
            return {k: self._substitute_env_vars(v) for k, v in obj.items()}
        
        elif isinstance(obj, list):
            return [self._substitute_env_vars(item) for item in obj]
        
        else:
            return obj
    
    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge com valores default."""
        defaults = self._get_default_config()
        return self._deep_merge(defaults, config)
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Merge profundo de dicionários."""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Valida a configuração."""
        validator = ConfigValidator()
        
        # Valida estrutura
        errors = validator.validate_config(config)
        
        # Valida tipos
        type_errors = validator.validate_types(config)
        errors.extend(type_errors)
        
        if errors:
            error_msg = "Erros de configuração encontrados:\n"
            error_msg += "\n".join(f"  - {error}" for error in errors)
            raise ConfigurationError(error_msg)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Retorna configuração padrão mínima."""
        return {
            'system': {
                'update_interval': 0.1,
                'log_dir': 'logs',
                'log_level': 'INFO',
                'environment': 'production'
            },
            'excel': {
                'sheet': 'Sheet1',
                'connection_timeout': 30,
                'retry_attempts': 3
            },
            'logging': {
                'buffer_size': 1000,
                'flush_interval': 5,
                'rotation': {
                    'max_size_mb': 100,
                    'backup_count': 5
                }
            },
            'monitoring': {
                'enabled': True,
                'metrics': {
                    'collect_interval': 60
                }
            },
            'debug': {
                'enabled': False
            }
        }
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Obtém uma seção específica da configuração.
        
        Args:
            section: Nome da seção
            
        Returns:
            Configuração da seção
        """
        config = self.load()
        return config.get(section, {})
    
    def reload(self) -> Dict[str, Any]:
        """Força recarga da configuração."""
        self._config_cache = None
        self._last_modified = None
        return self.load()


# Funções de conveniência
@lru_cache(maxsize=1)
def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """
    Carrega configurações (com cache).
    
    Args:
        config_path: Caminho do arquivo de configuração
        
    Returns:
        Dicionário de configuração
    """
    loader = ConfigLoader(config_path)
    return loader.load()


def get_config_value(path: str, default: Any = None) -> Any:
    """
    Obtém valor específico da configuração.
    
    Args:
        path: Caminho no formato 'section.subsection.key'
        default: Valor padrão se não encontrar
        
    Returns:
        Valor da configuração ou default
    """
    config = load_config()
    
    keys = path.split('.')
    value = config
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


# Carrega configuração padrão ao importar
try:
    DEFAULT_CONFIG = load_config()
except Exception as e:
    logger.warning(f"Não foi possível carregar configuração padrão: {e}")
    DEFAULT_CONFIG = {}


# Atalhos para configurações comuns
class Settings:
    """Classe com atalhos para configurações comuns."""
    
    @staticmethod
    def get_log_level() -> str:
        return get_config_value('system.log_level', 'INFO')
    
    @staticmethod
    def get_environment() -> str:
        return get_config_value('system.environment', 'production')
    
    @staticmethod
    def is_debug() -> bool:
        return get_config_value('debug.enabled', False)
    
    @staticmethod
    def get_excel_file() -> str:
        return get_config_value('excel.file', 'rtd_tapeReading.xlsx')
    
    @staticmethod
    def get_update_interval() -> float:
        return get_config_value('system.update_interval', 0.1)


# Exporta as principais classes e funções
__all__ = [
    'ConfigLoader',
    'ConfigValidator', 
    'ConfigurationError',
    'load_config',
    'get_config_value',
    'Settings',
    'DEFAULT_CONFIG'
]