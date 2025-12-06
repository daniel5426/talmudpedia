import os
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from pinecone import Pinecone, ServerlessSpec
import time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

class VectorStore:
    def __init__(self, index_name: str = "talmudpedia"):
        # Initialize Google GenAI
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.embedding_model = "gemini-embedding-001"

        # Initialize Pinecone
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
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
            result = self.client.models.embed_content(
                model=self.embedding_model,
                contents=[text],
                config=types.EmbedContentConfig(task_type="QUESTION_ANSWERING")
                )
            return result.embeddings[0].values
        except Exception as e:
            print(f"Error embedding text: {e}")
            return []

    def embed_batch_text(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embedding for a batch of text strings with max 100 elements per call.
        """
        if not texts:
            return []
        
        all_embeddings = []
        batch_size = 100
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                result = self.client.models.embed_content(
                    model=self.embedding_model,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type="QUESTION_ANSWERING")
                )
                all_embeddings.extend([emb.values for emb in result.embeddings])
            except Exception as e:
                print(f"Error embedding batch text: {e}")
                all_embeddings.extend([[] for _ in batch])
        
        return all_embeddings


    def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        """
        Upsert a batch of chunks to Pinecone using batch embedding.
        """
        if not chunks:
            return
        
        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embed_batch_text(texts)
        
        if not embeddings or len(embeddings) != len(chunks):
            print(f"Error: Expected {len(chunks)} embeddings, got {len(embeddings) if embeddings else 0}")
            return
        
        vectors = []
        for chunk, embedding in zip(chunks, embeddings):
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

    def search(self, query_text: str, limit: int = 10, filter_by_parent: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search the vector store for similar chunks.
        Optionally filter by parent title to retrieve only chunks from children of the specified node.
        """
        query_embedding = self.embed_text(query_text)
        if not query_embedding:
            return []
        
        filter_dict = None
        if filter_by_parent:
            filter_dict = {
                "parent_titles": {"$in": [filter_by_parent]}
            }
        
        try:
            query_params = {
                "vector": query_embedding,
                "top_k": limit,
                "include_metadata": True
            }
            if filter_dict:
                query_params["filter"] = filter_dict
            
            results = self.index.query(**query_params)
            
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
