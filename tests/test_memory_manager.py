import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from chat.memory.manager import MemoryManager, MemoryConfig
from chat.memory.base import MemoryItem

@pytest.mark.manager
class TestMemoryManager:
    @pytest.fixture
    def mock_config(self):
        return MemoryConfig(
            working_memory_capacity=2,
            episodic_memory_retention_days=30
        )

    @pytest.fixture
    def manager(self, mock_config):
        # Mock 掉底层的具体 Memory 类，避免连接真实数据库
        with patch("chat.memory.manager.WorkingMemory") as MockWorking, \
             patch("chat.memory.manager.EpisodicMemory") as MockEpisodic, \
             patch("chat.memory.manager.SemanticMemory") as MockSemantic:
            
            mgr = MemoryManager(config=mock_config)
            yield mgr

    def test_initialization(self, mock_config):
        with patch("chat.memory.manager.WorkingMemory"), \
             patch("chat.memory.manager.EpisodicMemory"), \
             patch("chat.memory.manager.SemanticMemory"):
            
            mgr = MemoryManager(config=mock_config, enable_semantic=False)
            assert "working" in mgr.memory_types
            assert "episodic" in mgr.memory_types
            assert "semantic" not in mgr.memory_types

    def test_add_memory(self, manager):
        # Setup mocks
        manager.memory_types["working"].add.return_value = "mem-id-1"
        
        # Action
        mid = manager.add_memory("test content", memory_type="working")
        
        # Assert
        assert mid == "mem-id-1"
        manager.memory_types["working"].add.assert_called_once()
        args, _ = manager.memory_types["working"].add.call_args
        assert isinstance(args[0], MemoryItem)
        assert args[0].content == "test content"

    def test_add_memory_invalid_type(self, manager):
        with pytest.raises(ValueError):
            manager.add_memory("content", memory_type="invalid_type")

    def test_retrieve_memory(self, manager):
        # Setup mocks
        mock_item = MagicMock(spec=MemoryItem)
        manager.memory_types["working"].retrieve.return_value = [mock_item]
        manager.memory_types["episodic"].retrieve.return_value = []
        
        # Action
        results = manager.retrieve_memory("query", memory_type=["working", "episodic"])
        
        # Assert
        assert "working" in results
        assert len(results["working"]) == 1
        assert "episodic" in results
        assert len(results["episodic"]) == 0
        
        manager.memory_types["working"].retrieve.assert_called_once()
        manager.memory_types["episodic"].retrieve.assert_called_once()

    def test_forget_transfer_integration(self, mock_config):
        # 使用真实的 WorkingMemory，Mock EpisodicMemory
        # 设置容量为 1，方便触发遗忘
        mock_config.working_memory_capacity = 1
        
        with patch("chat.memory.manager.EpisodicMemory") as MockEpisodic, \
             patch("chat.memory.manager.SemanticMemory"):
            
            mock_episodic_instance = MockEpisodic.return_value
            
            # 初始化 Manager，此时 WorkingMemory 是真实的
            manager = MemoryManager(config=mock_config, enable_semantic=False)
            
            # 添加第一个记忆
            manager.add_memory("mem1", "working")
            
            # 添加第二个记忆，应该触发 mem1 的遗忘
            manager.add_memory("mem2", "working")
            
            # 验证 EpisodicMemory.add 被调用
            mock_episodic_instance.add.assert_called()
            args, _ = mock_episodic_instance.add.call_args
            item = args[0]
            assert item.content == "mem1"
            assert item.memory_type == "episodic"

    @pytest.mark.anyio
    @pytest.mark.parametrize("anyio_backend", ["asyncio"])
    async def test_consolidate_memories(self, manager):
        # Mock LLM Client
        mock_llm = MagicMock()
        mock_llm.model = "gpt-test"
        mock_llm.async_client.chat.completions.create = AsyncMock()
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "memories": [
                {"content": "User likes AI", "importance": 0.9}
            ]
        })
        mock_llm.async_client.chat.completions.create.return_value = mock_response
        
        # Mock Episodic Memory data
        mock_episodic = manager.memory_types["episodic"]
        mock_mem = MemoryItem(
            id="ep-1", content="I like AI", memory_type="episodic",
            user_id="u1", group_id="g1", timestamp=datetime.now()
        )
        mock_episodic.get_unconsolidated_memories.return_value = [mock_mem]
        
        # Mock Semantic Memory
        mock_semantic = manager.memory_types["semantic"]
        
        # Action
        await manager.consolidate_memories(mock_llm, limit=5)
        
        # Assert
        # 1. Check LLM called
        mock_llm.async_client.chat.completions.create.assert_called_once()
        
        # 2. Check Semantic added
        mock_semantic.add.assert_called()
        args, _ = mock_semantic.add.call_args
        added_item = args[0]
        assert added_item.content == "User likes AI"
        assert added_item.metadata["importance"] == 0.9
        assert added_item.metadata["source_episodic_ids"] == ["ep-1"]
        
        # 3. Check Episodic marked
        mock_episodic.mark_as_consolidated.assert_called_once_with(["ep-1"])
