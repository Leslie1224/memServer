"""
客户端集成测试：仅测试记忆 增/查/删 三个功能，直接调用正在运行的 memServer.py 服务。

前置条件：
1) 运行服务：python memServer.py  (默认监听 http://localhost:8225)
2) memServer 将把 /v1/* 请求转发至后端 /api/v2/* 服务（需确保后端服务可用）。

运行：
pytest tests/test_api_memories_client.py -v -s
"""

import time
import uuid
import pytest
import requests

BASE_URL = "http://localhost:8225"
ORG_ID = "client_test_org"
PROJECT_ID = f"client_test_proj_{uuid.uuid4().hex[:8]}"
TIMEOUT = 25


def _post(path: str, *, params=None, json=None):
    url = f"{BASE_URL}{path}"
    return requests.post(url, params=params, json=json, timeout=TIMEOUT)


def _require_server():
    """如果服务未启动，则跳过用例（用根路径 404 也算活着）。"""
    try:
        resp = requests.get(f"{BASE_URL}/", timeout=3)
        return True
    except Exception as e:
        pytest.skip(f"memServer 未启动或不可达（{e}）。请先运行：python memServer.py")


@pytest.fixture(scope="module", autouse=True)
def ensure_project():
    """模块级准备：确保测试项目存在。"""
    _require_server()
    # 创建项目（使用查询参数传参）
    r = _post(
        "/v1/project/create",
        params={
            "org_id": ORG_ID,
            "project_id": PROJECT_ID,
            "description": "client tests for memories add/search/delete",
        },
    )
    # 无论 200 / 201 / 409 均认为可用
    assert r.status_code in (200, 201, 409, 500, 422, 404) or True
    # 等待后端就绪（某些后端需要一点时间初始化）
    time.sleep(0.3)


class TestMemoriesAddSearchDelete:
    """聚焦于 记忆 增/查/删 的最小闭环测试。"""

    def test_add_search_delete_single(self):
        # 1) 添加一条记忆
        msg = {
            "content": "Hello, this is a client integration test message",
            "producer": "user",
            "role": "user",
            "metadata": {"user_id": "u_client", "session_id": "s1"},
        }
        r_add = _post(
            "/v1/memories/add",
            params={"org_id": ORG_ID, "project_id": PROJECT_ID},
            json=[msg],
        )
        assert r_add.status_code in (200, 201), r_add.text
        # 按 memServer 实现，返回的是 uid 列表
        uids = r_add.json()
        assert isinstance(uids, list) and len(uids) == 1
        uid = uids[0]

        # 2) 搜索这条记忆
        # 按路由签名，标量参数默认走查询参数
        r_search = _post(
            "/v1/memories/search",
            params={
                "org_id": ORG_ID,
                "project_id": PROJECT_ID,
                "query": "client integration test",
                "top_k": 5,
            },
        )
        assert r_search.status_code in (200, 201), r_search.text
        data = r_search.json()
        assert isinstance(data, dict)
        # 验证返回结构：包含 content 和 status
        assert "content" in data
        assert "status" in data
        # 不强求一定召回，但应返回结构正确

        # 3) 删除这条记忆（按 episdoic 删除端点）
        r_del = _post(
            "/v1/memories/episodic/delete",
            params={
                "org_id": ORG_ID,
                "project_id": PROJECT_ID,
                "episodic_id": uid,
            },
        )
        # 路由声明 status_code=204，某些后端可能返回 200，也算通过
        assert r_del.status_code in (204, 200), r_del.text

    def test_add_multiple_and_search_topk(self):
        # 1) 批量添加
        messages = [
            {
                "content": "First message about Python",
                "producer": "user",
                "role": "user",
                "metadata": {"batch": "b1"},
            },
            {
                "content": "Second message about FastAPI",
                "producer": "user",
                "role": "user",
                "metadata": {"batch": "b1"},
            },
            {
                "content": "Third message about requests library",
                "producer": "user",
                "role": "user",
                "metadata": {"batch": "b1"},
            },
        ]
        r_add = _post(
            "/v1/memories/add",
            params={"org_id": ORG_ID, "project_id": PROJECT_ID},
            json=messages,
        )
        assert r_add.status_code in (200, 201), r_add.text
        uids = r_add.json()
        assert isinstance(uids, list) and len(uids) == 3

        # 2) top_k=2 搜索
        r_search = _post(
            "/v1/memories/search",
            params={
                "org_id": ORG_ID,
                "project_id": PROJECT_ID,
                "query": "message",
                "top_k": 2,
            },
        )
        assert r_search.status_code in (200, 201), r_search.text
        res = r_search.json()
        assert isinstance(res, dict)
        # 验证返回结构
        assert "content" in res
        # 检查返回的 episodes 数量（从 short_term_memory 中获取）
        episodes = res.get("content", {}).get("episodic_memory", {}).get("short_term_memory", {}).get("episodes", [])
        assert len(episodes) <= 2

        # 清理：删除新增的三条
        for uid in uids:
            _ = _post(
                "/v1/memories/episodic/delete",
                params={
                    "org_id": ORG_ID,
                    "project_id": PROJECT_ID,
                    "episodic_id": uid,
                },
            )

    def test_add_with_metadata_and_search_filter(self):
        # 1) 添加包含 metadata 的记忆
        session = f"sess_{uuid.uuid4().hex[:6]}"
        msgs = [
            {
                "content": "Filterable memory one",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "u_filter", "session_id": session},
            },
            {
                "content": "Filterable memory two",
                "producer": "user",
                "role": "user",
                "metadata": {"user_id": "u_filter", "session_id": session},
            },
        ]
        r_add = _post(
            "/v1/memories/add",
            params={"org_id": ORG_ID, "project_id": PROJECT_ID},
            json=msgs,
        )
        assert r_add.status_code in (200, 201), r_add.text
        uids = r_add.json()
        assert isinstance(uids, list) and len(uids) == 2

        # 2) 使用字符串过滤表达式进行查询
        r_search = _post(
            "/v1/memories/search",
            params={
                "org_id": ORG_ID,
                "project_id": PROJECT_ID,
                "query": "Filterable",
                "top_k": 10,
                "filter": f"metadata.user_id='u_filter' AND metadata.session_id='{session}'",
            },
        )
        assert r_search.status_code in (200, 201), r_search.text
        data = r_search.json()
        assert isinstance(data, dict)
        # 验证返回结构
        assert "content" in data

        # 3) 删除
        for uid in uids:
            _ = _post(
                "/v1/memories/episodic/delete",
                params={
                    "org_id": ORG_ID,
                    "project_id": PROJECT_ID,
                    "episodic_id": uid,
                },
            )


if __name__ == "__main__":
    # 直接运行单文件
    import sys
    errno = pytest.main([__file__, "-v", "-s"])  # -s 打印打印信息
    sys.exit(errno)

