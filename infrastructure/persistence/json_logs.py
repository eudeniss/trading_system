#infrastructure/persistence/json_logs.py
"""Repositório de logs JSON otimizado."""
import json
import logging
from pathlib import Path
from datetime import datetime
from collections import deque
import threading
import time
from typing import Any, Dict, Optional
import numpy as np

from core.entities.signal import Signal
from core.contracts.repository import ISignalRepository

logger = logging.getLogger(__name__)

# Tenta importar orjson para performance
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False
    logger.warning("orjson não instalado. Usando json padrão (mais lento). Instale com: pip install orjson")


class JsonLogRepository(ISignalRepository):
    """
    Implementação de ISignalRepository que salva logs em formato JSON Lines (.jsonl)
    de forma assíncrona, otimizada e segura para ambientes com múltiplas threads.
    """
    
    __slots__ = ['log_dir', 'buffers', 'locks', 'flush_interval', 'running', 
                 'writer_thread', '_serialization_cache', '_cache_hits', 
                 '_cache_misses', '_save_counters']
    
    def __init__(self, log_dir: str = 'logs', flush_interval: int = 5):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Buffers para armazenar logs em memória antes de escrever no disco
        self.buffers = {
            'signals': deque(),
            'arbitrage': deque(),
            'tape_reading': deque(),
            'system': deque()
        }
        
        # Locks para garantir thread safety
        self.locks = {name: threading.Lock() for name in self.buffers.keys()}
        
        self.flush_interval = flush_interval
        
        # Cache de serialização para objetos complexos frequentes
        self._serialization_cache = {}
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Contadores de salvamento para debug
        self._save_counters = {name: 0 for name in self.buffers.keys()}
        
        # Thread de escrita em background
        self.running = True
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()
        
        logger.info(
            f"JsonLogRepository inicializado - log_dir: {self.log_dir}, "
            f"flush_interval: {flush_interval}s, orjson: {HAS_ORJSON}"
        )

    def _convert_to_serializable(self, obj: Any) -> Any:
        """Converte objetos complexos para formato serializável com suporte a NumPy 2.0."""
        # Trata tipos NumPy primeiro (compatível com NumPy 2.0)
        if isinstance(obj, (np.integer, np.int8, np.int16, np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.complex64, np.complex128)):
            return {'real': float(obj.real), 'imag': float(obj.imag)}
        
        # Tenta cache para Enums
        if hasattr(obj, '__hash__') and hasattr(obj, 'value'):  # Enum
            cache_key = (type(obj), obj.value)
            if cache_key in self._serialization_cache:
                self._cache_hits += 1
                return self._serialization_cache[cache_key]
            else:
                self._cache_misses += 1
                serialized = obj.value
                self._serialization_cache[cache_key] = serialized
                return serialized
        
        # Para outros tipos, continua a conversão normal
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, 'dict'):  # Pydantic models
            return self._convert_to_serializable(obj.dict())
        elif isinstance(obj, dict):
            return {k: self._convert_to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._convert_to_serializable(item) for item in obj]
        elif isinstance(obj, set):
            return list(obj)  # Converte sets para listas
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # Última tentativa - converte para string
            return str(obj)

    def save(self, signal: Signal) -> None:
        """Salva um sinal no buffer de forma segura."""
        try:
            log_entry = self._convert_to_serializable(signal.dict())
            log_entry['_saved_at'] = datetime.now().isoformat()
            
            with self.locks['signals']:
                self.buffers['signals'].append(log_entry)
                self._save_counters['signals'] += 1
                
            # Log periódico
            if self._save_counters['signals'] % 100 == 0:
                logger.debug(f"Sinais salvos: {self._save_counters['signals']}")
                
        except Exception as e:
            logger.error(f"Erro ao preparar sinal para log: {e}", exc_info=True)

    def save_arbitrage_check(self, arbitrage_data: dict) -> None:
        """Salva dados de arbitragem no buffer de forma segura."""
        try:
            serializable_data = self._convert_to_serializable(arbitrage_data)
            
            # Garante que sempre tem timestamp
            if 'timestamp' not in serializable_data:
                serializable_data['timestamp'] = datetime.now().isoformat()
            
            # Adiciona metadados úteis
            serializable_data['_saved_at'] = datetime.now().isoformat()
            serializable_data['_has_opportunities'] = bool(arbitrage_data.get('spreads'))
            
            # Extrai informações úteis se disponíveis
            if 'spreads' in arbitrage_data and isinstance(arbitrage_data['spreads'], dict):
                best = arbitrage_data['spreads'].get('best', {})
                serializable_data['_best_profit'] = float(best.get('profit', 0))
                serializable_data['_best_spread'] = float(best.get('spread', 0))
                serializable_data['_is_profitable'] = bool(best.get('is_profitable', False))
                
            # Salva no buffer com lock
            with self.locks['arbitrage']:
                self.buffers['arbitrage'].append(serializable_data)
                self._save_counters['arbitrage'] += 1
            
            # Log periódico de estatísticas
            if self._save_counters['arbitrage'] % 100 == 0:
                logger.info(
                    f"📊 Arbitragem: {self._save_counters['arbitrage']} verificações salvas no log"
                )
                
        except Exception as e:
            logger.error(f"Erro ao salvar arbitrage_check: {e}", exc_info=True)

    def save_tape_reading_pattern(self, tape_data: dict) -> None:
        """Salva padrões de tape reading no buffer de forma segura."""
        try:
            serializable_data = self._convert_to_serializable(tape_data)
            
            # Adiciona timestamp se não existir
            if 'timestamp' not in serializable_data:
                serializable_data['timestamp'] = datetime.now().isoformat()
            
            serializable_data['_saved_at'] = datetime.now().isoformat()
            
            # Extrai padrão se disponível
            if 'pattern' in tape_data:
                serializable_data['_pattern_type'] = tape_data['pattern']

            with self.locks['tape_reading']:
                self.buffers['tape_reading'].append(serializable_data)
                self._save_counters['tape_reading'] += 1
                
            # Log periódico
            if self._save_counters['tape_reading'] % 100 == 0:
                logger.debug(f"Tape patterns salvos: {self._save_counters['tape_reading']}")
                
        except Exception as e:
            logger.error(f"Erro ao salvar tape_reading_pattern: {e}", exc_info=True)

    def _writer_loop(self) -> None:
        """Loop de escrita em background."""
        logger.info("Thread de escrita de logs iniciada")
        
        while self.running:
            try:
                time.sleep(self.flush_interval)
                self.flush()
            except Exception as e:
                logger.error(f"Erro no loop de escrita: {e}", exc_info=True)
                
        logger.info("Thread de escrita de logs finalizada")

    def flush(self) -> None:
        """Move os logs dos buffers para os arquivos de log."""
        start_time = time.perf_counter()
        total_written = 0
        
        for log_type, buffer in self.buffers.items():
            if not buffer:
                continue
            
            # Drena o buffer de forma thread-safe
            items_to_write = []
            with self.locks[log_type]:
                # Copia todas as mensagens do buffer de uma vez
                items_to_write.extend(buffer)
                buffer.clear()

            if items_to_write:
                written = self._write_batch_append(log_type, items_to_write)
                total_written += written
        
        # Log de performance se demorou muito
        elapsed = time.perf_counter() - start_time
        if elapsed > 1.0:  # Mais de 1 segundo
            logger.warning(f"Flush demorou {elapsed:.2f}s para escrever {total_written} items")
    
    def _custom_json_encoder(self, obj):
        """Encoder customizado para json.dump quando orjson não está disponível."""
        if isinstance(obj, (np.integer, np.int8, np.int16, np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, datetime):
            return obj.isoformat()
        else:
            return str(obj)
    
    def _write_batch_append(self, log_type: str, batch: list) -> int:
        """
        Escreve um lote de logs usando serialização otimizada.
        Retorna quantidade de items escritos.
        """
        if not batch:
            return 0

        # Usa extensão .jsonl para indicar JSON Lines
        file_path = self.log_dir / f"{log_type}.jsonl"
        
        try:
            if HAS_ORJSON:
                # Modo otimizado com orjson
                with open(file_path, 'ab') as f:  # Modo binário append
                    for item in batch:
                        try:
                            # Garante conversão completa antes de serializar
                            clean_item = self._deep_convert_numpy(item)
                            
                            f.write(orjson.dumps(
                                clean_item,
                                option=orjson.OPT_APPEND_NEWLINE | orjson.OPT_UTC_Z
                            ))
                        except TypeError as e:
                            # Se ainda falhar, tenta conversão mais agressiva
                            logger.warning(f"Erro ao serializar com orjson, tentando conversão completa: {e}")
                            super_clean_item = json.loads(json.dumps(item, default=self._custom_json_encoder))
                            f.write(orjson.dumps(
                                super_clean_item,
                                option=orjson.OPT_APPEND_NEWLINE | orjson.OPT_UTC_Z
                            ))
            else:
                # Fallback para json padrão com encoder customizado
                with open(file_path, 'a', encoding='utf-8') as f:
                    for item in batch:
                        json.dump(item, f, ensure_ascii=False, default=self._custom_json_encoder)
                        f.write('\n')
            
            # Log detalhado para arbitragem
            if log_type == 'arbitrage' and len(batch) > 0:
                logger.debug(f"Batch de {len(batch)} arbitragens escritas em {file_path}")
            
            return len(batch)
            
        except Exception as e:
            logger.error(
                f"Erro ao escrever batch de {len(batch)} logs para {log_type}: {e}", 
                exc_info=True
            )
            return 0
    
    def _deep_convert_numpy(self, obj):
        """Converte recursivamente todos os tipos numpy em um objeto."""
        if isinstance(obj, (np.integer, np.int8, np.int16, np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: self._deep_convert_numpy(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._deep_convert_numpy(item) for item in obj]
        else:
            return obj

    def close(self) -> None:
        """Finaliza o repositório de forma segura, garantindo que todos os logs sejam salvos."""
        logger.info("Finalizando JsonLogRepository...")
        
        # Para a thread de escrita
        self.running = False
        
        # Espera a thread terminar
        if self.writer_thread.is_alive():
            self.writer_thread.join(timeout=self.flush_interval + 1)
        
        # Faz um flush final
        logger.info("Realizando flush final dos logs...")
        self.flush()
        
        # Log de estatísticas finais
        logger.info("Estatísticas finais de salvamento:")
        for log_type, count in self._save_counters.items():
            if count > 0:
                logger.info(f"  {log_type}: {count} items salvos")
        
        # Log estatísticas do cache de serialização
        if self._cache_hits > 0 or self._cache_misses > 0:
            total = self._cache_hits + self._cache_misses
            hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
            logger.info(
                f"Cache de serialização: {self._cache_hits} hits, "
                f"{self._cache_misses} misses ({hit_rate:.1f}% hit rate)"
            )
        
        logger.info("JsonLogRepository finalizado com sucesso")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas do repositório."""
        stats = {
            'save_counters': dict(self._save_counters),
            'buffer_sizes': {name: len(buffer) for name, buffer in self.buffers.items()},
            'cache_stats': {
                'hits': self._cache_hits,
                'misses': self._cache_misses,
                'hit_rate': (self._cache_hits / (self._cache_hits + self._cache_misses) * 100) 
                           if (self._cache_hits + self._cache_misses) > 0 else 0
            },
            'log_files': {}
        }
        
        # Verifica tamanho dos arquivos
        for log_type in self.buffers.keys():
            file_path = self.log_dir / f"{log_type}.jsonl"
            if file_path.exists():
                stats['log_files'][log_type] = {
                    'exists': True,
                    'size_bytes': file_path.stat().st_size,
                    'size_mb': file_path.stat().st_size / (1024 * 1024)
                }
            else:
                stats['log_files'][log_type] = {'exists': False}
        
        return stats