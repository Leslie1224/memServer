"""
test_memServer.py

memServer.py API 接口的客户端测试
- 以客户端形式直接调用服务器的 API 接口
- 测试记忆的增删查功能

前置条件：
1. 启动 memServer.py 服务：python memServer.py
2. 服务运行在 http://localhost:8225

运行方式：
pytest test_memServer.py -v
或
python -m pytest test_memServer.py -v
"""

import pytest
import requests
import time
from memServer import MemoryServer


# 配置
BASE_URL = "http://localhost:8225"
ORG_ID = "test_org"
PROJECT_ID = "test_project"
TIMEOUT = 10


class TestAddMemories:
    """测试添加记忆功能"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前准备"""
        self.server = MemoryServer(base_url=BASE_URL, timeout=TIMEOUT)
        yield
        # 测试后清理（可选）

    def test_add_memories_single(self):
        """测试添加单条记忆"""
        messages = [
            {
                "content": "Hello, this is a test message",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "test_user_1", "session_id": "session_1"}
            }
        ]
        
        response = self.server.add_memories(ORG_ID, PROJECT_ID, messages)
        
        assert response.status_code == 201 or response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 1
        assert "uid" in data["results"][0]
        print(f"✓ 添加单条记忆成功，UID: {data['results'][0]['uid']}")

    def test_add_memories_multiple(self):
        """测试添加多条记忆"""
        messages = [
            {
                "content": "First message",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "test_user_1"}
            },
            {
                "content": "Second message",
                "producer": "agent",
                "role": "assistant",
                "metadata": {"user_id": "test_user_1"}
            },
            {
                "content": "Third message",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "test_user_1"}
            }
        ]
        
        response = self.server.add_memories(ORG_ID, PROJECT_ID, messages)
        
        assert response.status_code in [200, 201]
        data = response.json()
        assert len(data["results"]) == 3
        print(f"✓ 添加3条记忆成功")

    def test_add_messages_simple(self):
        """测试简单添加消息"""
        contents = [
            "Simple message 1",
            "Simple message 2",
            "Simple message 3"
        ]
        
        response_obj = self.server.add_messages_simple(
            ORG_ID, PROJECT_ID,
            contents,
            producer="user",
            role="user",
            metadata={"session_id": "test_session"}
        )
        
        # add_messages_simple 返回 uid 列表
        assert isinstance(response_obj, list)
        assert len(response_obj) == 3
        print(f"✓ 简单添加3条消息成功，UIDs: {response_obj}")

    def test_add_episodic_memory(self):
        """测试添加 episodic 记忆"""
        messages = [
            {
                "content": "User asked about Python programming",
                "producer": "user",
                "role": "user",
                "metadata": {
                    "user_id": "test_user_1",
                    "timestamp": str(int(time.time()))
                }
            }
        ]
        
        response_obj = self.server.add_episodic(ORG_ID, PROJECT_ID, messages)
        
        assert isinstance(response_obj, list)
        assert len(response_obj) == 1
        print(f"✓ 添加 episodic 记忆成功，UID: {response_obj[0]}")

    def test_add_semantic_memory(self):
        """测试添加 semantic 记忆"""
        messages = [
            {
                "content": "Python is a high-level programming language known for its simplicity",
                "producer": "system",
                "role": "system",
                "metadata": {"category": "knowledge"}
            }
        ]
        
        response_obj = self.server.add_semantic(ORG_ID, PROJECT_ID, messages)
        
        assert isinstance(response_obj, list)
        assert len(response_obj) == 1
        print(f"✓ 添加 semantic 记忆成功，UID: {response_obj[0]}")


class TestSearchMemories:
    """测试查询记忆功能"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前准备"""
        self.server = MemoryServer(base_url=BASE_URL, timeout=TIMEOUT)
        
        # 添加测试数据
        messages = [
            {
                "content": "Python programming tutorial",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "search_test_user"}
            },
            {
                "content": "How to learn Python effectively",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "search_test_user"}
            },
            {
                "content": "Java is another programming language",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "search_test_user"}
            }
        ]
        self.server.add_memories(ORG_ID, PROJECT_ID, messages)
        time.sleep(1)  # 等待索引更新
        
        yield

    def test_search_memories_basic(self):
        """测试基本搜索"""
        result = self.server.search_memories(ORG_ID, PROJECT_ID, "Python")
        
        assert isinstance(result, dict)
        assert "results" in result
        assert len(result["results"]) > 0
        print(f"✓ 搜索 'Python' 成功，找到 {len(result['results'])} 条结果")

    def test_search_memories_with_top_k(self):
        """测试搜索并指定返回数量"""
        result = self.server.search_memories(
            ORG_ID, PROJECT_ID, "programming",
            top_k=2
        )
        
        assert isinstance(result, dict)
        assert "results" in result
        # 返回的结果数量不超过 top_k
        assert len(result["results"]) <= 2
        print(f"✓ 搜索 'programming' (top_k=2) 成功，返回 {len(result['results'])} 条结果")

    def test_search_memories_with_filter(self):
        """测试搜索并使用过滤条件"""
        result = self.server.search_memories(
            ORG_ID, PROJECT_ID, "Python",
            filter="metadata.user_id='search_test_user'"
        )
        
        assert isinstance(result, dict)
        assert "results" in result
        print(f"✓ 搜索 'Python' (带过滤条件) 成功，找到 {len(result['results'])} 条结果")

    def test_search_memories_with_types(self):
        """测试搜索并指定记忆类型"""
        result = self.server.search_memories(
            ORG_ID, PROJECT_ID, "programming",
            types=["episodic"]
        )
        
        assert isinstance(result, dict)
        assert "results" in result
        print(f"✓ 搜索 'programming' (episodic 类型) 成功，找到 {len(result['results'])} 条结果")

    def test_search_memories_no_result(self):
        """测试搜索无结果"""
        result = self.server.search_memories(
            ORG_ID, PROJECT_ID, "xyzabc123nonexistent"
        )
        
        assert isinstance(result, dict)
        assert "results" in result
        assert len(result["results"]) == 0
        print(f"✓ 搜索不存在的关键词，正确返回空结果")

    def test_search_memories_all_parameters(self):
        """测试搜索使用所有参数"""
        result = self.server.search_memories(
            ORG_ID, PROJECT_ID, "Python",
            top_k=5,
            filter="metadata.user_id='search_test_user'",
            types=["episodic", "semantic"]
        )
        
        assert isinstance(result, dict)
        assert "results" in result
        print(f"✓ 搜索使用所有参数成功，找到 {len(result['results'])} 条结果")


class TestListMemories:
    """测试列表记忆功能"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前准备"""
        self.server = MemoryServer(base_url=BASE_URL, timeout=TIMEOUT)
        
        # 添加测试数据
        messages = [
            {
                "content": f"List test message {i}",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "list_test_user", "index": str(i)}
            }
            for i in range(5)
        ]
        self.server.add_memories(ORG_ID, PROJECT_ID, messages)
        time.sleep(1)
        
        yield

    def test_list_memories_default(self):
        """测试默认列表参数"""
        result = self.server.list_memories(ORG_ID, PROJECT_ID)
        
        assert isinstance(result, dict)
        assert "data" in result or "results" in result
        print(f"✓ 列表记忆成功，获取数据")

    def test_list_memories_with_pagination(self):
        """测试分页列表"""
        result = self.server.list_memories(
            ORG_ID, PROJECT_ID,
            page_size=2,
            page_num=0
        )
        
        assert isinstance(result, dict)
        data = result.get("data") or result.get("results")
        assert data is not None
        print(f"✓ 分页列表成功 (page_size=2, page_num=0)，获取 {len(data)} 条记录")

    def test_list_memories_episodic_type(self):
        """测试列表 episodic 类型记忆"""
        result = self.server.list_memories(
            ORG_ID, PROJECT_ID,
            type_="episodic"
        )
        
        assert isinstance(result, dict)
        print(f"✓ 列表 episodic 类型记忆成功")

    def test_list_memories_semantic_type(self):
        """测试列表 semantic 类型记忆"""
        result = self.server.list_memories(
            ORG_ID, PROJECT_ID,
            type_="semantic"
        )
        
        assert isinstance(result, dict)
        print(f"✓ 列表 semantic 类型记忆成功")

    def test_list_memories_with_filter(self):
        """测试列表并使用过滤条件"""
        result = self.server.list_memories(
            ORG_ID, PROJECT_ID,
            filter="metadata.user_id='list_test_user'"
        )
        
        assert isinstance(result, dict)
        print(f"✓ 列表记忆 (带过滤条件) 成功")

    def test_list_memories_all_parameters(self):
        """测试列表使用所有参数"""
        result = self.server.list_memories(
            ORG_ID, PROJECT_ID,
            page_size=10,
            page_num=0,
            filter="metadata.user_id='list_test_user'",
            type_="episodic"
        )
        
        assert isinstance(result, dict)
        print(f"✓ 列表记忆 (所有参数) 成功")


class TestDeleteMemories:
    """测试删除记忆功能"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前准备"""
        self.server = MemoryServer(base_url=BASE_URL, timeout=TIMEOUT)
        
        # 添加待删除的测试数据
        messages = [
            {
                "content": "Message to be deleted 1",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "delete_test_user"}
            },
            {
                "content": "Message to be deleted 2",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "delete_test_user"}
            }
        ]
        self.uids = self.server.add_memories(ORG_ID, PROJECT_ID, messages)
        time.sleep(1)
        
        yield

    def test_delete_episodic_memory(self):
        """测试删除 episodic 记忆"""
        if not self.uids:
            pytest.skip("没有可删除的记忆")
        
        uid_to_delete = self.uids[0]
        response = self.server.delete_episodic(ORG_ID, PROJECT_ID, uid_to_delete)
        
        # 删除成功返回 None 或 204 状态码
        assert response is None or response.status_code == 204
        print(f"✓ 删除 episodic 记忆成功，UID: {uid_to_delete}")

    def test_delete_semantic_memory(self):
        """测试删除 semantic 记忆"""
        if not self.uids:
            pytest.skip("没有可删除的记忆")
        
        uid_to_delete = self.uids[0]
        response = self.server.delete_semantic(ORG_ID, PROJECT_ID, uid_to_delete)
        
        # 删除成功返回 None 或 204 状态码
        assert response is None or response.status_code == 204
        print(f"✓ 删除 semantic 记忆成功，UID: {uid_to_delete}")

    def test_delete_multiple_memories(self):
        """测试删除多条记忆"""
        if len(self.uids) < 2:
            pytest.skip("没有足够的记忆用于删除测试")
        
        for uid in self.uids:
            response = self.server.delete_episodic(ORG_ID, PROJECT_ID, uid)
            assert response is None or response.status_code == 204
        
        print(f"✓ 删除 {len(self.uids)} 条记忆成功")


class TestCompleteWorkflow:
    """测试完整的增删查工作流"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前准备"""
        self.server = MemoryServer(base_url=BASE_URL, timeout=TIMEOUT)
        yield

    def test_workflow_add_search_delete(self):
        """工作流：添加 -> 查询 -> 删除"""
        # 1. 添加记忆
        messages = [
            {
                "content": "Workflow test message about machine learning",
                "producer": "user",
                "role": "user",
                "metadata": {"workflow": "test_1"}
            }
        ]
        uids = self.server.add_memories(ORG_ID, PROJECT_ID, messages)
        assert len(uids) == 1
        print(f"✓ 步骤1: 添加记忆成功，UID: {uids[0]}")
        
        time.sleep(1)  # 等待索引更新
        
        # 2. 查询记忆
        result = self.server.search_memories(
            ORG_ID, PROJECT_ID, "machine learning"
        )
        assert len(result["results"]) > 0
        print(f"✓ 步骤2: 查询记忆成功，找到 {len(result['results'])} 条结果")
        
        # 3. 删除记忆
        response = self.server.delete_episodic(ORG_ID, PROJECT_ID, uids[0])
        assert response is None or response.status_code == 204
        print(f"✓ 步骤3: 删除记忆成功")

    def test_workflow_add_list_delete(self):
        """工作流：添加 -> 列表 -> 删除"""
        # 1. 添加多条记忆
        messages = [
            {
                "content": f"Workflow list test message {i}",
                "producer": "user",
                "role": "user",
                "metadata": {"workflow": "test_2", "index": str(i)}
            }
            for i in range(3)
        ]
        uids = self.server.add_memories(ORG_ID, PROJECT_ID, messages)
        assert len(uids) == 3
        print(f"✓ 步骤1: 添加3条记忆成功")
        
        time.sleep(1)
        
        # 2. 列表记忆
        result = self.server.list_memories(
            ORG_ID, PROJECT_ID,
            filter="metadata.workflow='test_2'"
        )
        data = result.get("data") or result.get("results")
        assert data is not None
        print(f"✓ 步骤2: 列表记忆成功，获取数据")
        
        # 3. 删除所有记忆
        for uid in uids:
            response = self.server.delete_episodic(ORG_ID, PROJECT_ID, uid)
            assert response is None or response.status_code == 204
        print(f"✓ 步骤3: 删除3条记忆成功")

    def test_workflow_add_episodic_semantic_search(self):
        """工作流：添加 episodic 和 semantic -> 查询"""
        # 1. 添加 episodic 记忆
        episodic_msgs = [
            {
                "content": "User asked about deep learning",
                "producer": "user",
                "role": "user",
                "metadata": {"workflow": "test_3", "type": "episodic"}
            }
        ]
        episodic_uids = self.server.add_episodic(ORG_ID, PROJECT_ID, episodic_msgs)
        print(f"✓ 步骤1: 添加 episodic 记忆成功")
        
        # 2. 添加 semantic 记忆
        semantic_msgs = [
            {
                "content": "Deep learning is a subset of machine learning",
                "producer": "system",
                "role": "system",
                "metadata": {"workflow": "test_3", "type": "semantic"}
            }
        ]
        semantic_uids = self.server.add_semantic(ORG_ID, PROJECT_ID, semantic_msgs)
        print(f"✓ 步骤2: 添加 semantic 记忆成功")
        
        time.sleep(1)
        
        # 3. 查询所有类型
        result = self.server.search_memories(
            ORG_ID, PROJECT_ID, "deep learning",
            types=["episodic", "semantic"]
        )
        assert len(result["results"]) > 0
        print(f"✓ 步骤3: 查询成功，找到 {len(result['results'])} 条结果")


class TestErrorHandling:
    """测试错误处理"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前准备"""
        self.server = MemoryServer(base_url=BASE_URL, timeout=TIMEOUT)
        yield

    def test_search_with_invalid_org(self):
        """测试使用无效的组织 ID 搜索"""
        result = self.server.search_memories(
            "invalid_org_xyz", "invalid_proj_xyz", "test"
        )
        # 应该返回空结果或错误
        assert isinstance(result, dict)
        print(f"✓ 无效组织 ID 处理成功")

    def test_add_memories_with_empty_content(self):
        """测试添加空内容的记忆"""
        messages = [
            {
                "content": "",
                "producer": "user",
                "role": "user",
                "metadata": {}
            }
        ]
        
        response = self.server.add_memories(ORG_ID, PROJECT_ID, messages)
        # 应该成功添加或返回错误
        assert response.status_code in [200, 201, 400, 422]
        print(f"✓ 空内容记忆处理成功")

    def test_delete_nonexistent_memory(self):
        """测试删除不存在的记忆"""
        response = self.server.delete_episodic(
            ORG_ID, PROJECT_ID, "nonexistent_uid_xyz123"
        )
        # 应该返回 404 或 204
        assert response is None or response.status_code in [204, 404]
        print(f"✓ 删除不存在的记忆处理成功")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
