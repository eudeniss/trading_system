#core/entities/book.py
"""Entidade OrderBook - representa o livro de ofertas."""
from pydantic import BaseModel, Field
from typing import List


class BookLevel(BaseModel):
    """Representa um nível de preço no livro de ofertas."""
    price: float = Field(gt=0, description="Preço do nível")
    volume: int = Field(ge=0, description="Volume no nível")
    
    class Config:
        frozen = True


class OrderBook(BaseModel):
    """Representa o livro de ofertas de um ativo."""
    bids: List[BookLevel] = Field(default_factory=list)
    asks: List[BookLevel] = Field(default_factory=list)

    @property
    def best_bid(self) -> float:
        """Retorna o melhor preço de compra."""
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        """Retorna o melhor preço de venda."""
        return self.asks[0].price if self.asks else 0.0
    
    @property
    def spread(self) -> float:
        """Retorna o spread (diferença entre ask e bid)."""
        if self.best_bid > 0 and self.best_ask > 0:
            return self.best_ask - self.best_bid
        return 0.0
    
    class Config:
        frozen = True