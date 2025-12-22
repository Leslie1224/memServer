"""
完整的 MemMachine 测试用例套件（已对齐 API v2）

本套件覆盖：
1. 项目管理 (创建、获取、删除)
2. 记忆操作 (添加、搜索、列出)
3. 过滤与元数据（通过 metadata 传入自定义上下文）
4. 错误处理与边界用例（Unicode、特殊字符、大文本）

重要差异（与旧示例相比）：
- 添加记忆路径：POST /api/v2/memories（或 /memories/episodic/add、/memories/semantic/add）
- 添加记忆请求体：仅需 org_id、project_id、messages；user_id/agent_id/session_id 等上下文请放入 messages[*].metadata
- 搜索参数：使用 top_k，而非 limit；filter 是字符串表达式（如 "metadata.user_id='u1'"）
- 列表接口：/api/v2/memories/list 使用 page_size/page_num/type
- 删除项目：/api/v2/projects/delete 返回 204
- 搜索与列表响应：返回 { status, content: { episodic_memory, semantic_memory } }

要求：
- MemMachine 服务器运行在 http://localhost:8080
- PostgreSQL 可用
- 可选：Ollama 或 OpenAI API 用于 LLM 功能
"""

import time
import json
import requests
from typing import Dict
from uuid import uuid4


class MemMachineTestSuite:
    """MemMachine 完整测试套件（API v2）"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_id = str(uuid4())[:8]
        self.test_results = []

    def log(self, message: str, level: str = "INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")

    def assert_equal(self, actual, expected, message: str = ""):
        if actual != expected:
            raise AssertionError(f"断言失败: {message}\n期望: {expected}\n实际: {actual}")

    def assert_true(self, condition: bool, message: str = ""):
        if not condition:
            raise AssertionError(f"断言失败: {message}")

    def assert_in(self, item, container, message: str = ""):
        if item not in container:
            raise AssertionError(f"断言失败: {message}\n{item} 不在 {container} 中")

    def record_test(self, test_name: str, status: str, message: str = ""):
        self.test_results.append({
            "test_name": test_name,
            "status": status,
            "message": message,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    # ------------- 调试辅助：打印请求与响应 -------------
    def _pp(self, obj) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            return str(obj)

    def _log_request(self, method: str, path: str, payload: dict):
        self.log(f"HTTP 请求 -> {method} {path}\npayload = {self._pp(payload)}")

    def _log_response(self, response):
        try:
            body = response.json()
        except Exception:
            body = response.text
        self.log(f"HTTP 响应 <- {response.status_code}\nbody = {self._pp(body)}")

    def _extract_episodic_from_search(self, data: dict):
        """从 /memories/search 的响应中尽量提取事件记忆列表，兼容多种结构。
        优先合并 short_term_memory.episodes 与 long_term_memory.episodes；
        回退到顶层 episodes/items/results/data。
        """
        content = (data or {}).get("content", {})
        em = content.get("episodic_memory")
        out = []
        # 直接是列表
        if isinstance(em, list):
            return em
        # 可能是 dict，深入分支
        if isinstance(em, dict):
            for branch in ("short_term_memory", "long_term_memory"):
                eps = ((em.get(branch) or {}).get("episodes")) or []
                if isinstance(eps, list):
                    out.extend(eps)
            # 兼容旧结构
            for key in ("episodes", "items", "results", "data"):
                val = em.get(key)
                if isinstance(val, list):
                    out.extend(val)
        return out

    def _summarize_episodes(self, episodes: list[dict]) -> list[dict]:
        """提炼输出：仅打印关键信息，便于人工核对。"""
        out = []
        for ep in episodes or []:
            if isinstance(ep, dict):
                md = ep.get("metadata") or {}
                out.append({
                    "uid": ep.get("uid") or ep.get("id"),
                    "content": ep.get("content"),
                    "metadata": {
                        "user_id": md.get("user_id"),
                        "agent_id": md.get("agent_id"),
                        "session_id": md.get("session_id"),
                    },
                })
            else:
                out.append({"raw": str(ep)})
        return out

    # ==================== 健康检查 ====================

    def test_health_check(self):
        test_name = "健康检查"
        try:
            self.log(f"开始测试: {test_name}")
            response = self.session.get(f"{self.base_url}/api/v2/health")
            self.assert_equal(response.status_code, 200, "健康检查应返回 200")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    # ==================== 项目管理测试 ====================

    def test_create_project(self) -> Dict[str, str]:
        test_name = "创建项目"
        try:
            self.log(f"开始测试: {test_name}")
            org_id = f"test_org_{self.test_id}"
            project_id = f"test_project_{self.test_id}"
            payload = {
                "org_id": org_id,
                "project_id": project_id,
                "description": "测试项目",
                "config": {"embedder": "", "reranker": ""},
            }
            response = self.session.post(f"{self.base_url}/api/v2/projects", json=payload)
            self.assert_equal(response.status_code, 201, "创建项目应返回 201")
            data = response.json()
            self.assert_equal(data["org_id"], org_id, "org_id 应匹配")
            self.assert_equal(data["project_id"], project_id, "project_id 应匹配")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
            return {"org_id": org_id, "project_id": project_id}
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    def test_get_project(self, org_id: str, project_id: str):
        test_name = "获取项目"
        try:
            self.log(f"开始测试: {test_name}")
            payload = {"org_id": org_id, "project_id": project_id}
            response = self.session.post(f"{self.base_url}/api/v2/projects/get", json=payload)
            self.assert_equal(response.status_code, 200, "获取项目应返回 200")
            data = response.json()
            self.assert_equal(data["org_id"], org_id, "org_id 应匹配")
            self.assert_equal(data["project_id"], project_id, "project_id 应匹配")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    def test_get_nonexistent_project(self):
        test_name = "获取不存在的项目"
        try:
            self.log(f"开始测试: {test_name}")
            payload = {"org_id": "nonexistent_org", "project_id": "nonexistent_project"}
            response = self.session.post(f"{self.base_url}/api/v2/projects/get", json=payload)
            self.assert_equal(response.status_code, 404, "应返回 404")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    def test_create_duplicate_project(self, org_id: str, project_id: str):
        test_name = "创建重复项目"
        try:
            self.log(f"开始测试: {test_name}")
            payload = {
                "org_id": org_id,
                "project_id": project_id,
                "description": "重复项目",
                "config": {"embedder": "", "reranker": ""},
            }
            response = self.session.post(f"{self.base_url}/api/v2/projects", json=payload)
            self.assert_equal(response.status_code, 409, "应返回 409 冲突")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    # ==================== 记忆操作测试 ====================

    def test_add_memory(self, org_id: str, project_id: str) -> str:
        test_name = "添加记忆"
        try:
            self.log(f"开始测试: {test_name}")
            user_id = f"user_{self.test_id}"
            agent_id = f"agent_{self.test_id}"
            session_id = f"session_{self.test_id}"
            payload = {
                "org_id": org_id,
                "project_id": project_id,
                "messages": [
                    {
                        "content": "我是一名软件工程师，喜欢 Python 编程",
                        "producer": "user",
                        "role": "user",
                        "metadata": {
                            "user_id": user_id,
                            "agent_id": agent_id,
                            "session_id": session_id,
                        },
                    }
                ],
            }
            path = f"{self.base_url}/api/v2/memories"
            self._log_request("POST", path, payload)
            response = self.session.post(path, json=payload)
            self._log_response(response)
            self.assert_equal(response.status_code, 200, "添加记忆应返回 200")
            data = response.json()
            self.assert_in("results", data, "响应应包含 results")
            self.assert_true(len(data.get("results", [])) >= 1, "应返回至少 1 个 uid")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
            return user_id
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    def test_add_multiple_memories(self, org_id: str, project_id: str, user_id: str):
        test_name = "添加多条记忆"
        try:
            self.log(f"开始测试: {test_name}")
            agent_id = f"agent_{self.test_id}"
            session_id = f"session_{self.test_id}"
            messages = [
                {
                    "content": "我喜欢在周末去登山",
                    "producer": "user",
                    "role": "user",
                    "metadata": {"user_id": user_id, "agent_id": agent_id, "session_id": session_id},
                },
                {
                    "content": "登山是很好的户外活动",
                    "producer": "assistant",
                    "role": "assistant",
                    "metadata": {"user_id": user_id, "agent_id": agent_id, "session_id": session_id},
                },
                {
                    "content": "我的最爱颜色是蓝色",
                    "producer": "user",
                    "role": "user",
                    "metadata": {"user_id": user_id, "agent_id": agent_id, "session_id": session_id},
                },
                {
                    "content": "我更喜欢咖啡而不是茶",
                    "producer": "user",
                    "role": "user",
                    "metadata": {"user_id": user_id, "agent_id": agent_id, "session_id": session_id},
                },
            ]
            payload = {"org_id": org_id, "project_id": project_id, "messages": messages}
            path = f"{self.base_url}/api/v2/memories"
            self._log_request("POST", path, payload)
            response = self.session.post(path, json=payload)
            self._log_response(response)
            self.assert_equal(response.status_code, 200, "添加多条记忆应返回 200")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    def test_search_memory(self, org_id: str, project_id: str, user_id: str):
        test_name = "搜索记忆"
        try:
            self.log(f"开始测试: {test_name}")
            time.sleep(2)  # 等待索引
            payload = {
                "org_id": org_id,
                "project_id": project_id,
                "query": "编程",
                "top_k": 10,
            }
            path = f"{self.base_url}/api/v2/memories/search"
            self._log_request("POST", path, payload)
            response = self.session.post(path, json=payload)
            self._log_response(response)
            self.assert_equal(response.status_code, 200, "搜索记忆应返回 200")
            data = response.json()
            self.assert_in("content", data, "响应应包含 content")
            content = data["content"]
            self.assert_true(isinstance(content, dict), "content 应为对象")
            self.assert_in("episodic_memory", content, "应包含 episodic_memory")
            self.assert_in("semantic_memory", content, "应包含 semantic_memory")
            self.log(
                f"✓ {test_name} 通过 - episodic={len(content.get('episodic_memory', []))}",
                "PASS",
            )
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    def test_search_with_filter(self, org_id: str, project_id: str, user_id: str):
        test_name = "带过滤的搜索"
        try:
            self.log(f"开始测试: {test_name}")
            payload = {
                "org_id": org_id,
                "project_id": project_id,
                "query": "喜欢",
                "top_k": 10,
                "filter": f"metadata.user_id='{user_id}'",
            }
            path = f"{self.base_url}/api/v2/memories/search"
            self._log_request("POST", path, payload)
            response = self.session.post(path, json=payload)
            self._log_response(response)
            self.assert_equal(response.status_code, 200, "带过滤的搜索应返回 200")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    def test_list_memories(self, org_id: str, project_id: str, user_id: str):
        test_name = "列出记忆"
        try:
            self.log(f"开始测试: {test_name}")
            payload = {
                "org_id": org_id,
                "project_id": project_id,
                "page_size": 10,
                "page_num": 0,
                "type": "episodic",
            }
            response = self.session.post(f"{self.base_url}/api/v2/memories/list", json=payload)
            self.assert_equal(response.status_code, 200, "列出记忆应返回 200")
            data = response.json()
            self.assert_in("content", data, "响应应包含 content")
            content = data["content"]
            self.assert_in("episodic_memory", content, "应包含 episodic_memory")
            self.log(
                f"✓ {test_name} 通过 - 列出 {len(content.get('episodic_memory', []))} 条",
                "PASS",
            )
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    def test_user_filter_isolation(self, org_id: str, project_id: str):
        test_name = "两用户过滤隔离"
        try:
            self.log(f"开始测试: {test_name}")
            u1 = f"user_a_{self.test_id}"
            u2 = f"user_b_{self.test_id}"
            agent = f"agent_{self.test_id}"
            s1 = f"session_{self.test_id}_1"
            s2 = f"session_{self.test_id}_2"
            messages = [
                {
                    "content": "U1: 我喜欢 Python 和科幻书籍",
                    "producer": "user",
                    "role": "user",
                    "metadata": {"user_id": u1, "agent_id": agent, "session_id": s1},
                },
                {
                    "content": "U2: 我喜欢 JavaScript 和美食",
                    "producer": "user",
                    "role": "user",
                    "metadata": {"user_id": u2, "agent_id": agent, "session_id": s2},
                },
                {
                    "content": "U1: 我周末常去登山",
                    "producer": "user",
                    "role": "user",
                    "metadata": {"user_id": u1, "agent_id": agent, "session_id": s1},
                },
                {
                    "content": "U2: 我更喜欢咖啡",
                    "producer": "user",
                    "role": "user",
                    "metadata": {"user_id": u2, "agent_id": agent, "session_id": s2},
                },
            ]
            payload = {"org_id": org_id, "project_id": project_id, "messages": messages}
            path_add = f"{self.base_url}/api/v2/memories"
            self._log_request("POST", path_add, payload)
            resp = self.session.post(path_add, json=payload)
            self._log_response(resp)
            self.assert_equal(resp.status_code, 200, "批量添加两用户记忆应返回 200")
            time.sleep(2)
            # user1 过滤
            path_search = f"{self.base_url}/api/v2/memories/search"
            search_payload_u1 = {
                "org_id": org_id,
                "project_id": project_id,
                "query": "喜欢",
                "top_k": 20,
                "filter": f"metadata.user_id='{u1}'",
                "types": ["episodic"],
            }
            self._log_request("POST", path_search, search_payload_u1)
            r1 = self.session.post(path_search, json=search_payload_u1)
            self._log_response(r1)
            self.assert_equal(r1.status_code, 200, "user1 过滤搜索应返回 200")
            data1 = r1.json()
            epis1 = self._extract_episodic_from_search(data1)
            # 打印提取后的简要答案（仅关键信息）
            self.log(f"user1 结果摘要: {self._pp(self._summarize_episodes(epis1))}")
            for ep in epis1:
                if isinstance(ep, dict):
                    md = ep.get("metadata", {}) or {}
                    if "user_id" in md:
                        self.assert_equal(md.get("user_id"), u1, "过滤后不应包含其他用户的记忆")
            # user2 过滤
            search_payload_u2 = {
                "org_id": org_id,
                "project_id": project_id,
                "query": "喜欢",
                "top_k": 20,
                "filter": f"metadata.user_id='{u2}'",
                "types": ["episodic"],
            }
            self._log_request("POST", path_search, search_payload_u2)
            r2 = self.session.post(path_search, json=search_payload_u2)
            self._log_response(r2)
            self.assert_equal(r2.status_code, 200, "user2 过滤搜索应返回 200")
            data2 = r2.json()
            epis2 = self._extract_episodic_from_search(data2)
            # 打印提取后的简要答案（仅关键信息）
            self.log(f"user2 结果摘要: {self._pp(self._summarize_episodes(epis2))}")
            for ep in epis2:
                if isinstance(ep, dict):
                    md = ep.get("metadata", {}) or {}
                    if "user_id" in md:
                        self.assert_equal(md.get("user_id"), u2, "过滤后不应包含其他用户的记忆")
            # 使用 list + filter 再做一次原始事件级校验（仅 episodic）
            path_list = f"{self.base_url}/api/v2/memories/list"
            list_payload_u1 = {
                "org_id": org_id,
                "project_id": project_id,
                "page_size": 50,
                "page_num": 0,
                "type": "episodic",
                "filter": f"metadata.user_id='{u1}'",
            }
            self._log_request("POST", path_list, list_payload_u1)
            lr1 = self.session.post(path_list, json=list_payload_u1)
            self._log_response(lr1)
            self.assert_equal(lr1.status_code, 200, "user1 列表过滤应返回 200")
            ld1 = lr1.json()
            le1 = (ld1.get("content", {}) or {}).get("episodic_memory", []) or []
            self.log(f"user1 列表结果摘要: {self._pp(self._summarize_episodes(le1))}")
            for ep in le1:
                if isinstance(ep, dict):
                    md = ep.get("metadata", {}) or {}
                    if "user_id" in md:
                        self.assert_equal(md.get("user_id"), u1, "列表过滤不应包含其他用户的记忆")

            list_payload_u2 = {
                "org_id": org_id,
                "project_id": project_id,
                "page_size": 50,
                "page_num": 0,
                "type": "episodic",
                "filter": f"metadata.user_id='{u2}'",
            }
            self._log_request("POST", path_list, list_payload_u2)
            lr2 = self.session.post(path_list, json=list_payload_u2)
            self._log_response(lr2)
            self.assert_equal(lr2.status_code, 200, "user2 列表过滤应返回 200")
            ld2 = lr2.json()
            le2 = (ld2.get("content", {}) or {}).get("episodic_memory", []) or []
            self.log(f"user2 列表结果摘要: {self._pp(self._summarize_episodes(le2))}")
            for ep in le2:
                if isinstance(ep, dict):
                    md = ep.get("metadata", {}) or {}
                    if "user_id" in md:
                        self.assert_equal(md.get("user_id"), u2, "列表过滤不应包含其他用户的记忆")

            # 至少有一边返回结果
            self.assert_true(len(epis1) + len(epis2) >= 1 or len(le1) + len(le2) >= 1, "应能检索到至少一条过滤结果")
            self.log(f"✓ {test_name} 通过 - search(u1={len(epis1)}, u2={len(epis2)}), list(u1={len(le1)}, u2={len(le2)})", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    # ==================== 删除操作测试 ====================

    def test_delete_project(self, org_id: str, project_id: str):
        test_name = "删除项目"
        try:
            self.log(f"开始测试: {test_name}")
            payload = {"org_id": org_id, "project_id": project_id}
            response = self.session.post(f"{self.base_url}/api/v2/projects/delete", json=payload)
            self.assert_equal(response.status_code, 204, "删除项目应返回 204")
            # 验证项目已删除
            time.sleep(1)
            response = self.session.post(f"{self.base_url}/api/v2/projects/get", json=payload)
            self.assert_equal(response.status_code, 404, "删除后应返回 404")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    # ==================== 特殊字符和 Unicode 测试 ====================

    def test_unicode_memory(self):
        test_name = "Unicode 记忆"
        try:
            self.log(f"开始测试: {test_name}")
            org_id = f"test_org_unicode_{self.test_id}"
            project_id = f"test_project_unicode_{self.test_id}"
            # 创建项目
            payload = {
                "org_id": org_id,
                "project_id": project_id,
                "description": "Unicode 测试项目",
                "config": {"embedder": "", "reranker": ""},
            }
            response = self.session.post(f"{self.base_url}/api/v2/projects", json=payload)
            self.assert_equal(response.status_code, 201, "创建项目应成功")
            # 添加 Unicode 记忆
            msg_payload = {
                "org_id": org_id,
                "project_id": project_id,
                "messages": [
                    {
                        "content": "测试中文内容 🚀 日本語テスト émojis",
                        "producer": "user",
                        "role": "user",
                        "metadata": {"user_id": f"user_unicode_{self.test_id}"},
                    }
                ],
            }
            response = self.session.post(f"{self.base_url}/api/v2/memories", json=msg_payload)
            self.assert_equal(response.status_code, 200, "添加 Unicode 记忆应成功")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    def test_special_characters_memory(self):
        test_name = "特殊字符记忆"
        try:
            self.log(f"开始测试: {test_name}")
            org_id = f"test_org_special_{self.test_id}"
            project_id = f"test_project_special_{self.test_id}"
            # 创建项目
            payload = {
                "org_id": org_id,
                "project_id": project_id,
                "description": "特殊字符测试",
                "config": {"embedder": "", "reranker": ""},
            }
            response = self.session.post(f"{self.base_url}/api/v2/projects", json=payload)
            self.assert_equal(response.status_code, 201, "创建项目应成功")
            # 添加特殊字符记忆
            msg_payload = {
                "org_id": org_id,
                "project_id": project_id,
                "messages": [
                    {
                        "content": "特殊字符测试: !@#$%^&*()_+-=[]{}|;':\",./<>?",
                        "producer": "user",
                        "role": "user",
                        "metadata": {"user_id": f"user_special_{self.test_id}"},
                    }
                ],
            }
            response = self.session.post(f"{self.base_url}/api/v2/memories", json=msg_payload)
            self.assert_equal(response.status_code, 200, "添加特殊字符记忆应成功")
            self.log(f"✓ {test_name} 通过", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    # ==================== 大数据测试 ====================

    def test_large_memory_content(self):
        test_name = "大容量记忆"
        try:
            self.log(f"开始测试: {test_name}")
            org_id = f"test_org_large_{self.test_id}"
            project_id = f"test_project_large_{self.test_id}"
            # 创建项目
            payload = {
                "org_id": org_id,
                "project_id": project_id,
                "description": "大容量测试",
                "config": {"embedder": "", "reranker": ""},
            }
            response = self.session.post(f"{self.base_url}/api/v2/projects", json=payload)
            self.assert_equal(response.status_code, 201, "创建项目应成功")
            # 添加大容量记忆 (10KB)
            large_content = "A" * 10000
            msg_payload = {
                "org_id": org_id,
                "project_id": project_id,
                "messages": [
                    {
                        "content": large_content,
                        "producer": "user",
                        "role": "user",
                        "metadata": {"user_id": f"user_large_{self.test_id}"},
                    }
                ],
            }
            response = self.session.post(f"{self.base_url}/api/v2/memories", json=msg_payload)
            self.assert_equal(response.status_code, 200, "添加大容量记忆应成功")
            self.log(f"✓ {test_name} 通过 (10KB 内容)", "PASS")
            self.record_test(test_name, "PASS")
        except Exception as e:
            self.log(f"✗ {test_name} 失败: {str(e)}", "FAIL")
            self.record_test(test_name, "FAIL", str(e))
            raise

    # ==================== 测试报告 ====================

    def print_test_report(self):
        print("\n" + "=" * 80)
        print("MemMachine 测试报告".center(80))
        print("=" * 80)
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        total = len(self.test_results)
        print(f"\n总计: {total} 个测试")
        print(f"通过: {passed} 个 ✓")
        print(f"失败: {failed} 个 ✗")
        print(f"成功率: {(passed/total*100):.1f}%" if total > 0 else "成功率: N/A")
        print("\n详细结果:")
        print("-" * 80)
        for result in self.test_results:
            status_icon = "✓" if result["status"] == "PASS" else "✗"
            print(f"{status_icon} {result['test_name']:<30} [{result['status']}]")
            if result["message"]:
                print(f"  └─ {result['message']}")
        print("\n" + "=" * 80)

    def run_all_tests(self):
        """仅运行：健康检查 -> 创建项目 -> 两用户隔离检索 -> 删除项目。
        打印每一步详细的 HTTP 输入与输出，便于人工核对检索是否隔离成功。
        """
        self.log("开始运行 MemMachine 用户隔离检索用例（最小集）", "INFO")
        self.log(f"测试 ID: {self.test_id}", "INFO")
        self.log(f"服务器地址: {self.base_url}", "INFO")
        try:
            # 健康检查
            self.test_health_check()
            # 创建项目
            project_info = self.test_create_project()
            org_id = project_info["org_id"]
            project_id = project_info["project_id"]

            # self.test_add_memory(org_id, project_id)
            # 只测两用户隔离检索（包含：批量写入 -> 两次 search(episodic) -> 两次 list 验证）
            self.test_user_filter_isolation(org_id, project_id)
            # 删除项目
            self.test_delete_project(org_id, project_id)
            self.log("用户隔离检索用例运行完成", "INFO")
        except Exception as e:
            self.log(f"测试执行出错: {str(e)}", "ERROR")
        finally:
            self.print_test_report()


def main():
    import sys
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    suite = MemMachineTestSuite(base_url=base_url)
    suite.run_all_tests()


if __name__ == "__main__":
    main()
