import pytest
from unittest.mock import MagicMock, patch
from chat.rag.client import RAGClient

@pytest.mark.rag
class TestRAGClient:
    
    @pytest.fixture
    def mock_components(self):
        with patch("chat.rag.client.DocumentLoader") as MockLoader, \
             patch("chat.rag.client.StorageManager") as MockStorage, \
             patch("chat.rag.client.Ranker") as MockRanker, \
             patch("chat.rag.client.TextSplitter") as MockSplitter:
            
            # Setup Loader
            loader_instance = MockLoader.return_value
            loader_instance.load.return_value = "Mock document content."
            
            # Setup Splitter
            splitter_instance = MockSplitter.return_value
            splitter_instance.split.return_value = [
                {"id": "1", "content": "Chunk 1", "metadata": {"doc_id": "doc1", "start": 0}},
                {"id": "2", "content": "Chunk 2", "metadata": {"doc_id": "doc1", "start": 10}}
            ]
            
            # Setup Storage
            storage_instance = MockStorage.return_value
            storage_instance.search_vectors.return_value = [
                {"id": "1", "score": 0.9, "content": "Chunk 1", "metadata": {"doc_id": "doc1", "start": 0, "memory_id": "1"}},
                {"id": "2", "score": 0.8, "content": "Chunk 2", "metadata": {"doc_id": "doc1", "start": 10, "memory_id": "2"}}
            ]
            
            # Setup Ranker
            ranker_instance = MockRanker.return_value
            ranker_instance.compute_graph_signal.return_value = {"1": 0.5, "2": 0.3}
            ranker_instance.rank.return_value = [
                {"memory_id": "1", "score": 0.95, "content": "Chunk 1", "metadata": {"doc_id": "doc1"}},
                {"memory_id": "2", "score": 0.85, "content": "Chunk 2", "metadata": {"doc_id": "doc1"}}
            ]
            ranker_instance.rank_by_cross_encoder.return_value = [
                {"memory_id": "1", "score": 0.99, "content": "Chunk 1", "metadata": {"doc_id": "doc1"}},
                {"memory_id": "2", "score": 0.88, "content": "Chunk 2", "metadata": {"doc_id": "doc1"}}
            ]
            
            yield {
                "loader": loader_instance,
                "splitter": splitter_instance,
                "storage": storage_instance,
                "ranker": ranker_instance
            }

    def test_add_documents(self, mock_components):
        client = RAGClient()
        
        count = client.add_documents(["test.pdf"])
        
        assert count == 2
        mock_components["loader"].load.assert_called_with("test.pdf")
        mock_components["splitter"].split.assert_called()
        mock_components["storage"].index_chunks.assert_called()

    def test_search(self, mock_components):
        client = RAGClient()
        results = client.search("query")
        
        assert len(results) == 2
        mock_components["storage"].search_vectors.assert_called()

    def test_search_advanced(self, mock_components):
        client = RAGClient()
        results = client.search_advanced(
            "query", 
            enable_cross_encoder=True, 
            enable_graph_rerank=True,
            enable_expansion=False,
            enable_compression=False
        )
        
        assert len(results) == 2
        mock_components["storage"].search_vectors.assert_called()
        mock_components["ranker"].compute_graph_signal.assert_called()
        mock_components["ranker"].rank.assert_called()
        mock_components["ranker"].rank_by_cross_encoder.assert_called()

    def test_merge_snippets(self, mock_components):
        client = RAGClient()
        items = [
            {"content": "Hello world."},
            {"content": "This is RAG."}
        ]
        merged = client.merge_snippets(items)
        assert "Hello world." in merged
        assert "This is RAG." in merged
