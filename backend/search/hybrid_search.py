import faiss
import numpy as np
import logging
from typing import List, Dict
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class HybridSearch:
    def __init__(self):
        self.products = []
        self.bm25 = None
        self.faiss_index = None
        self.encoder = None
        self.is_ready = False

    def build_index(self, products: List[Dict]):
        """Khởi tạo/Rebuild cả BM25 và FAISS index từ danh sách sản phẩm"""
        if not products:
            logger.warning("No products provided to build search index.")
            return

        self.products = products
        
        # 1. Prepare search texts
        texts = [self._build_search_text(p) for p in products]
        
        # 2. Build BM25 Index (Sparse)
        tokenized_corpus = [self._tokenize(t) for t in texts]
        self.bm25 = BM25Okapi(tokenized_corpus)
        
        # 3. Build FAISS Index (Dense)
        # Sử dụng model hỗ trợ tiếng Việt & tiếng Anh nhỏ gọn, nhanh
        if not self.encoder:
            logger.info("Loading SentenceTransformer multilingual-e5-small...")
            self.encoder = SentenceTransformer("intfloat/multilingual-e5-small")
            
        logger.info("Encoding vectors for FAISS...")
        embeddings = self.encoder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        
        dim = embeddings.shape[1]
        self.faiss_index = faiss.IndexFlatIP(dim) # Inner product với normalized vector = Cosine similarity
        self.faiss_index.add(embeddings.astype("float32"))
        
        self.is_ready = True
        logger.info(f"Hybrid search index built with {len(products)} products.")

    def search(self, query: str, top_k: int = 15) -> List[str]:
        """Thực hiện Hybrid Search: BM25 + FAISS + RRF"""
        if not self.is_ready or not self.products:
            logger.warning("Search index not ready.")
            return []

        # 1. Sparse Search: BM25 (Top 50)
        bm25_scores = self.bm25.get_scores(self._tokenize(query))
        bm25_top_idx = np.argsort(bm25_scores)[::-1][:50].tolist()

        # 2. Dense Search: FAISS (Top 50)
        q_vec = self.encoder.encode([query], normalize_embeddings=True).astype("float32")
        _, faiss_top_idx_arr = self.faiss_index.search(q_vec, 50)
        faiss_top_idx = faiss_top_idx_arr[0].tolist()

        # 3. Fusion: Reciprocal Rank Fusion
        fused_indices = self._rrf([bm25_top_idx, faiss_top_idx], k=60)
        
        # 4. Return top K product IDs
        final_indices = fused_indices[:top_k]
        return [self.products[i]["id"] for i in final_indices]

    def _rrf(self, rankings: List[List[int]], k: int = 60) -> List[int]:
        """Reciprocal Rank Fusion"""
        scores = {}
        for ranking in rankings:
            for rank, idx in enumerate(ranking):
                if idx >= 0: # FAISS có thể trả về -1 nếu không đủ kết quả
                    scores[idx] = scores.get(idx, 0) + 1.0 / (k + rank + 1)
                    
        # Sort indices by score descending
        return sorted(scores.keys(), key=lambda idx: scores[idx], reverse=True)

    def _tokenize(self, text: str) -> List[str]:
        """Basic whitespace tokenizer, phù hợp với BM25 tiếng Việt cơ bản"""
        return text.lower().split()

    def _build_search_text(self, product: Dict) -> str:
        """Gộp các field thành 1 chuỗi dài để search"""
        parts = [
            product.get("name", ""),
            product.get("category", ""),
            product.get("description", ""),
            product.get("material", ""),
            product.get("style", ""),
            " ".join(product.get("print_techniques", []))
        ]
        return " ".join(p for p in parts if p).lower()

# Singleton instance
hybrid_searcher = HybridSearch()
