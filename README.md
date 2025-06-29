# Sistema de Trading DOL/WDO v7.0 - Clean Architecture + Cache Centralizado

## 📊 Visão Geral

Sistema profissional de análise de arbitragem estatística entre contratos DOL e WDO (mini-dólar e dólar cheio na B3), implementado com Clean Architecture e cache centralizado de alta performance. Combina detecção de padrões de tape reading, gestão de risco integrada e interface moderna em tempo real.

### 🎯 Principais Características

- **Clean Architecture**: Separação completa entre domínio, aplicação e infraestrutura
- **Cache Centralizado**: Sistema unificado de cache thread-safe para todos os serviços
- **Zero Persistência**: Operação sem estado persistente (opcional)
- **8+ Padrões de Tape Reading**: Absorção, divergências, momentum, pressão, icebergs, etc.
- **Gestão de Risco Integrada**: Circuit breakers, validação de qualidade, limites adaptativos
- **Detecção Anti-Manipulação**: Filtros contra layering, spoofing e padrões suspeitos
- **Interface Textual Moderna**: Display responsivo com Textual framework
- **Event-Driven Architecture**: Comunicação desacoplada via barramento de eventos

## 🏗️ Arquitetura do Sistema

### Estrutura de Diretórios

```
trading_system_v7/
├── domain/                      # Camada de Domínio (Entidades e Contratos)
│   ├── entities/               # Entidades de negócio
│   │   ├── trade.py           # Trade com validação Pydantic
│   │   ├── book.py            # OrderBook
│   │   ├── signal.py          # Sinais de trading
│   │   └── market_data.py     # Agregado de dados
│   └── repositories/           # Interfaces (contratos)
│       └── trade_cache.py      # Interface ITradeCache
│
├── application/                # Camada de Aplicação (Casos de Uso)
│   ├── services/              # Serviços de negócio
│   │   ├── arbitrage_service.py       # Lógica de arbitragem
│   │   ├── tape_reading_service.py    # Análise de fluxo (usa cache)
│   │   ├── confluence_service.py      # Confirmação de sinais
│   │   └── risk_management_service.py # Gestão de risco
│   └── interfaces/            # Portas (interfaces)
│       ├── market_data_provider.py
│       ├── signal_repository.py
│       └── system_event_bus.py
│
├── infrastructure/            # Camada de Infraestrutura (Implementações)
│   ├── cache/                # NOVO! Cache centralizado
│   │   ├── __init__.py
│   │   └── trade_memory_cache.py    # Implementação thread-safe
│   ├── data_sources/
│   │   └── excel_market_provider.py  # Leitor Excel/RTD
│   ├── event_bus/
│   │   └── local_event_bus.py       # Barramento de eventos
│   └── logging/
│       └── json_log_repository.py    # Logs JSON otimizados
│
├── analyzers/                # Algoritmos Especializados
│   ├── patterns/            # Detectores de padrões
│   │   ├── absorption_detector.py
│   │   ├── iceberg_detector.py
│   │   ├── momentum_analyzer.py
│   │   ├── pressure_detector.py
│   │   ├── volume_spike_detector.py
│   │   └── defensive_filter.py
│   ├── statistics/          # Calculadoras estatísticas
│   │   ├── cvd_calculator.py
│   │   ├── pace_analyzer.py
│   │   └── volume_profile_analyzer.py
│   ├── regimes/
│   │   ├── market_regime_detector.py
│   │   └── regime_translator.py
│   └── formatters/
│       └── signal_formatter.py
│
├── presentation/            # Camada de Apresentação
│   └── display/
│       ├── monitor_app.py   # Interface Textual
│       └── monitor_display.py
│
├── orchestration/          # Orquestração e Coordenação
│   ├── event_handlers.py   # Handlers de eventos
│   └── trading_system.py   # Sistema principal
│
├── config/
│   ├── config.yaml        # Configurações
│   └── settings.py        # Loader
│
└── main.py               # Ponto de entrada

```

## 🚀 Instalação Rápida

### Pré-requisitos

- Python 3.8+
- Microsoft Excel com dados RTD
- Windows (recomendado) ou macOS/Linux com Wine

### Instalação

```bash
# Clone o repositório
git clone <repo-url>
cd trading_system_v7

# Crie ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Instale dependências
pip install -r requirements.txt

# Execute
python main.py
```

## 📖 Guia de Interpretação dos Sinais

### 🟢 SINAIS DE COMPRA

#### 1. **Confluência (Máxima Confiança)**
```
🔥 COMPRA CONFIRMADA | Spread: 2.5pts (R$25) | Fluxo Comprador DOL [ALTA]
```
**Ação**: Comprar DOL + Vender WDO simultaneamente

#### 2. **Absorção Compradora**
```
🛡️ COMPRA | ABSORÇÃO COMPRADORA WDO @ 5680.50 | Vendedores absorvidos (Vol: 450)
```
**Significado**: Grande player absorvendo vendas neste nível (suporte forte)

#### 3. **Divergência Altista**
```
📈 COMPRA | Divergência Altista WDO: Preço cai, fluxo sobe (ROC: +120%)
```
**Significado**: Acumulação disfarçada, possível reversão para cima

### 🔴 SINAIS DE VENDA

#### 1. **Confluência de Venda**
```
🔥 VENDA CONFIRMADA | Spread: -2.0pts (R$20) | Fluxo Vendedor DOL [ALTA]
```
**Ação**: Vender DOL + Comprar WDO simultaneamente

#### 2. **Absorção Vendedora**
```
🛡️ VENDA | ABSORÇÃO VENDEDORA @ 5681.00 | Compradores absorvidos
```
**Significado**: Grande player distribuindo neste nível (resistência)

#### 3. **Divergência Baixista**
```
📉 VENDA | Divergência Baixista: Preço sobe, fluxo cai (ROC: -80%)
```
**Significado**: Distribuição em andamento, possível queda

### 📊 INDICADORES DE CONTEXTO

**No Header Principal**:
- **CVD Total**: Saldo acumulado de agressão (+ = mais compra, - = mais venda)
- **Momentum**: Direção da força atual (ALTA/BAIXA/NEUTRO)
- **Pressão**: Quem domina agora (COMPRA/VENDA/EQUILIBRADO)

**Risk Management**:
- 🟢 **Risco Baixo**: Operar normalmente
- 🟡 **Risco Médio**: Reduzir tamanho das posições
- 🟠 **Risco Alto**: Extrema cautela
- 🔴 **Risco Crítico**: NÃO OPERAR!

### ⚠️ ALERTAS DE MANIPULAÇÃO

```
🚨 WDO - CUIDADO ao COMPRAR! Book com ordens suspeitas na compra
```
**Ação**: Evitar operar na direção indicada

## 🎮 Operação do Sistema

### Interface Principal (Textual)

```
╔════════════════════════════════════════════════════════════════╗
║                    Sistema de Trading v7.0                      ║
║  CVD: WDO +621 | DOL -223  •  Pressão: COMPRA | VENDA         ║
╚════════════════════════════════════════════════════════════════╝

┌─ 📊 ARBITRAGEM ─────────┬─ 📈 TAPE READING ────────┬─ 🛡️ RISK MANAGEMENT ─┐
│ Spread: 2.5 pts (R$25)  │ WDO:                     │ 🟢 Risco Baixo       │
│ Z-Score: +1.8           │   CVD: +45 (Total: +621) │ [██░░░]              │
│ [══════█═══│═══════]    │   ROC: +14%              │                      │
│                         │   POC: 5680.50           │ 📊 Métricas:         │
│ Média: -0.89 pts        │                          │   ✓ Aprovação: 85.3% │
│ Desvio: 0.22            │ DOL:                     │   ⚡ Perdas: 0       │
│ Min/Max: -1.5/0.5       │   CVD: -23 (Total: -223) │   💰 PnL: R$45.00    │
│                         │   ROC: +800%             │   📉 DD: 0.5%        │
└─────────────────────────┴──────────────────────────┴──────────────────────┘

┌─ 📡 SINAIS ATIVOS ─────────────────────────────────────────────────────┐
│ 14:32:15 🔥 Confluence  COMPRA CONFIRMADA | Spread: 2.5pts | [ALTA]    │
│ 14:32:08 📊 Tape Read   ABSORÇÃO COMPRADORA WDO @ 5680.50             │
│ 14:31:45 💹 Tape Read   Pressão compradora WDO: 85% do volume         │
└────────────────────────────────────────────────────────────────────────┘
```

### Atalhos de Teclado

- **Q**: Sair do sistema
- **C**: Limpar sinais
- **R**: Forçar atualização

## 🔧 Configuração Avançada

### Cache Centralizado

```yaml
tape_reading:
  buffer_size: 10000  # Trades em memória por símbolo
```

**Estatísticas do Cache** (exibidas a cada minuto):
- Taxa de acerto (hit rate)
- Total de trades armazenados
- Número de evictions

### Parâmetros de Trading

```yaml
arbitrage:
  min_profit: 15.0      # Lucro mínimo em R$
  signal_cooldown: 30   # Segundos entre sinais

tape_reading:
  cvd_threshold: 150    # Threshold para sinal de CVD
  absorption_threshold: 282
  pressure_threshold: 0.75
```

### Risk Management

```yaml
risk_management:
  max_signals_per_minute: 5
  consecutive_losses_limit: 5
  max_drawdown_percent: 2.0
  emergency_stop_loss: 1000.0
```

## 📊 Logs e Análise

### Arquivos de Log

- `logs/signals.jsonl`: Todos os sinais (JSON Lines)
- `logs/arbitrage.jsonl`: Oportunidades de arbitragem
- `logs/tape_reading.jsonl`: Padrões detectados
- `logs/system.log`: Log geral do sistema

### Formato JSON Lines

Cada linha é um JSON completo, facilitando análise:

```bash
# Contar sinais de confluência
grep "CONFLUENCE" logs/signals.jsonl | wc -l

# Ver últimos 10 sinais
tail -10 logs/signals.jsonl | jq .
```

## 🚨 Troubleshooting

### Excel não conecta
1. Verifique se `rtd_tapeReading.xlsx` está aberto
2. Confirme o caminho em `config.yaml`
3. Feche outras instâncias do Excel

### Sem sinais aparecendo
1. Verifique se há movimento no mercado
2. Confira os thresholds no config
3. Veja o log para erros

### Performance/Latência
1. Reduza `buffer_size` se memória for problema
2. Aumente `update_interval` para menos atualizações
3. Desative logs desnecessários

## 🏆 Melhores Práticas

1. **Sempre aguarde confluência** para sinais de alta confiança
2. **Respeite os circuit breakers** - existem para sua proteção
3. **Monitore o regime de mercado** - ajuste estratégia conforme condições
4. **Use stops** baseados nos níveis de absorção detectados
5. **Evite operar** com alertas de manipulação ativos

## ⚖️ Aviso Legal

Este software é fornecido "como está" para fins educacionais. Trading envolve risco substancial de perda. Os desenvolvedores não se responsabilizam por perdas decorrentes do uso deste sistema.

## 📝 Changelog

### v7.0.0 (2024-01-27)
- Implementação completa com Clean Architecture
- Cache centralizado thread-safe
- Interface Textual moderna
- 8+ padrões de tape reading
- Sistema anti-manipulação
- Risk management integrado

---

**Desenvolvido com ❤️ para a comunidade de traders algorítmicos**

*Versão*: 7.0.0 | *Licença*: MIT