import os
from typing import List, Dict, Any
import google.generativeai as genai
from pinecone import Pinecone, ServerlessSpec
import time

class VectorStore:
    def __init__(self, pinecone_api_key: str, google_api_key: str, index_name: str = "talmudpedia"):
        # Initialize Google GenAI
        genai.configure(api_key=google_api_key)
        self.embedding_model = "models/embedding-001"

        # Initialize Pinecone
        self.pc = Pinecone(api_key=pinecone_api_key)
        self.index_name = index_name
        
        # Create index if not exists (simplified for serverless)
        if index_name not in self.pc.list_indexes().names():
            print(f"Creating index {index_name}...")
            self.pc.create_index(
                name=index_name,
                dimension=768, # Google embedding-001 dimension
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
        
        self.index = self.pc.Index(index_name)

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text string.
        """
        try:
            result = genai.embed_content(
                model=self.embedding_model,
                content=text,
                task_type="retrieval_document",
                title="Talmud Text"
            )
            return result['embedding']
        except Exception as e:
            print(f"Error embedding text: {e}")
            return []

    def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        """
        Upsert a batch of chunks to Pinecone.
        """
        vectors = []
        for chunk in chunks:
            embedding = self.embed_text(chunk["text"])
            if not embedding:
                print(f"Error embedding chunk: {chunk['id']}")
                continue
            
            vectors.append({
                "id": chunk["id"],
                "values": embedding,
                "metadata": chunk["metadata"]
            })
        
        if vectors:
            try:
                self.index.upsert(vectors=vectors)
                print(f"Upserted {len(vectors)} chunks.")
            except Exception as e:
                print(f"Error upserting to Pinecone: {e}")

    def search(self, query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search the vector store for similar chunks.
        """
        query_embedding = self.embed_text(query_text)
        if not query_embedding:
            return []
        
        try:
            results = self.index.query(
                vector=query_embedding,
                top_k=limit,
                include_metadata=True
            )
            
            matches = []
            for match in results['matches']:
                matches.append({
                    "id": match['id'],
                    "score": match['score'],
                    "metadata": match['metadata']
                })
            return matches
        except Exception as e:
            print(f"Error searching Pinecone: {e}")
            return []
