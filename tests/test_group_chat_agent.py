import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from chat.agents.group_chat_agent import GroupChatAgent
from chat.core.llm import LLMClient
from chat.core.config import Config
from chat.memory import MemoryConfig

@pytest.mark.agent
class TestGroupChatAgent:
    
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock(spec=LLMClient)
        llm.achat = AsyncMock(return_value="我是学姐，你好呀！")
        return llm

    @pytest.fixture
    def agent(self, mock_llm, tmp_path):
        # Mock Qdrant to avoid connection errors
        with patch("chat.memory.storage.qdrant_store.QdrantConnectionManager"), \
             patch("chat.memory.storage.neo4j_store.Neo4jGraphStore"):
            
            config = Config()
            mem_config = MemoryConfig(storage_path=str(tmp_path))
            
            agent = GroupChatAgent(
                name="TestAgent",
                llm=mock_llm,
                group_id="test_group",
                config=config,
                memory_config=mem_config,
                enable_memory=True
            )
            yield agent

    @pytest.mark.anyio
    @pytest.mark.parametrize("anyio_backend", ["asyncio"])
    async def test_run_flow(self, agent, mock_llm):
        # Test the full run flow
        query = "你好，学姐"
        user_id = "student_1"
        
        response = await agent.run(query)
        
        assert response == "我是学姐，你好呀！"
        
        # Verify LLM called
        mock_llm.achat.assert_called_once()
        call_args = mock_llm.achat.call_args
        messages = call_args.kwargs.get('messages')
        if not messages and call_args.args:
            messages = call_args.args[0]
        assert len(messages) == 2
        assert messages[1].content == query
        
        # Verify memory saved (Working Memory)
        # We need to check if memory manager has the memories
        # Since we use real MemoryManager (with mocked storage backends), we can check it.
        # WorkingMemory is in-memory (or sqlite? BaseMemory uses SQLiteDocumentStore).
        # WorkingMemory inherits BaseMemory, so it uses SQLite.
        
        # Check user query saved
        memories = agent.memory_manager.retrieve_memory(query, memory_type=["working"])
        working_mems = memories.get("working", [])
        # Should have user query AND assistant response
        # assert len(working_mems) >= 2
        # assert any(m.content == query for m in working_mems)
        # assert any(m.content == "我是学姐，你好呀！" for m in working_mems)
