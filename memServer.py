"""
memServer.py

简洁的 MemMachine REST API 封装，便于在测试或业务代码中直接调用。
- 覆盖 API v2 的主要端点（项目/记忆/检索/删除等）
- 对 requests 进行轻封装，提供明确的返回类型与错误信息
- 约定：抛出 requests.HTTPError 代表非 2xx 响应

用法：
from memServer import MemServer
api = MemServer(base_url="http://localhost:8080")
api.health()
api.create_project("org", "proj")
api.add_memories("org", "proj", messages=[...])
res = api.search_memories("org", "proj", query="关键词", top_k=10, types=["episodic"]) 

注意：
- 添加记忆时的 user_id/agent_id/session_id 请放到 messages[*]["metadata"] 中。
- /memories/search 的 filter 是字符串表达式，例如: "metadata.user_id='u1' AND metadata.session_id='s1'"。
"""
import uvicorn
import shutil
import json
import os
import glob
from typing import Any, List, Dict, Optional
from dataclasses import dataclass, asdict
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Body
from pydantic import BaseModel, Field
import requests

class MemoryServer:
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        session: Optional[requests.Session] = None,
        timeout: float = 30.0,
        logger: Optional[callable] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self._log = logger

    # -------------------- 内部工具 --------------------
    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _post(self, url: str, json) -> requests.Response:
        return requests.post(url, json=json, timeout=self.timeout)

    def _get(self, url: str) -> requests.Response:
        return requests.get(url, timeout=self.timeout)

    # -------------------- 运行与健康 --------------------
    def health(self):
        return self._get(f"{self.base_url}/api/v2/health")

    # -------------------- 项目管理 --------------------
    def create_project(
        self,
        org_id: str,
        project_id: str,
        description: str = "",
        embedder: str = "",
        reranker: str = "",
    ):
        payload = {
            "org_id": org_id,
            "project_id": project_id,
            "description": description,
            "config": {"embedder": embedder, "reranker": reranker},
        }
        return self._post(f"{self.base_url}/api/v2/projects", payload)
    def get_project(self, org_id: str, project_id: str):
        payload = {"org_id": org_id, "project_id": project_id}
        return self._post(f"{self.base_url}/api/v2/projects/get", payload)

    def get_or_create_project(
        self,
        org_id: str,
        project_id: str,
        description: str = "",
        *,
        embedder: str = "",
        reranker: str = "",
    ):
        try:
            return self.get_project(org_id, project_id)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return self.create_project(
                    org_id, project_id, description, embedder=embedder, reranker=reranker
                )
            raise

    def delete_project(self, org_id: str, project_id: str) -> None:
        payload = {"org_id": org_id, "project_id": project_id}
        self._post(f"{self.base_url}/api/v2/projects/delete", payload)
        # 204 也会被 raise_for_status 视为成功

    def episodes_count(self, org_id: str, project_id: str) -> int:
        payload = {"org_id": org_id, "project_id": project_id}
        return self._post(f"{self.base_url}/api/v2/projects/episode_count/get", payload).json().get("count", 0)

    def list_projects(self) -> List[Dict[str, str]]:
        return self._post(f"{self.base_url}/api/v2/projects/list", {}).json()

    # -------------------- 记忆添加 --------------------
    def add_memories(
        self,
        org_id: str,
        project_id: str,
        messages: List[Dict[str, Any]],
    ) -> List[str]:
        """添加记忆，返回 episode uid 列表。
        messages 形如：[{"content": str, "producer": str, "role": str, "metadata": {..}}]
        """
        payload = {"org_id": org_id, "project_id": project_id, "messages": messages}
        data = self._post(f"{self.base_url}/api/v2/memories", payload).json()
        return [item.get("uid") for item in data.get("results", [])]

    def add_messages_simple(
        self,
        org_id: str,
        project_id: str,
        contents: List[str],
        *,
        producer: str = "user",
        role: str = "user",
        metadata: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        messages = [
            {"content": c, "producer": producer, "role": role, "metadata": metadata or {}}
            for c in contents
        ]
        return self.add_memories(org_id, project_id, messages)

    def add_episodic(self, org_id: str, project_id: str, messages: List[Dict[str, Any]]) -> List[str]:
        payload = {"org_id": org_id, "project_id": project_id, "messages": messages}
        data = self._post(f"{self.base_url}/api/v2/memories/episodic/add", payload).json()
        return [item.get("uid") for item in data.get("results", [])]

    def add_semantic(self, org_id: str, project_id: str, messages: List[Dict[str, Any]]) -> List[str]:
        payload = {"org_id": org_id, "project_id": project_id, "messages": messages}
        data = self._post(f"{self.base_url}/api/v2/memories/semantic/add", payload).json()
        return [item.get("uid") for item in data.get("results", [])]

    # -------------------- 检索与列表 --------------------
    def search_memories(
        self,
        org_id: str,
        project_id: str,
        query: str,
        top_k: int = 10,
        filter: str = "",
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "org_id": org_id,
            "project_id": project_id,
            "query": query,
            "top_k": top_k,
        }
        if filter:
            payload["filter"] = filter
        if types:
            payload["types"] = types
        return self._post(f"{self.base_url}/api/v2/memories/search", payload).json()

    def list_memories(
        self,
        org_id: str,
        project_id: str,
        *,
        page_size: int = 100,
        page_num: int = 0,
        filter: str = "",
        type_: str = "episodic",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "org_id": org_id,
            "project_id": project_id,
            "page_size": page_size,
            "page_num": page_num,
            "type": type_,
        }
        if filter:
            payload["filter"] = filter
        return self._post(f"{self.base_url}/api/v2/memories/list", payload).json()

    # -------------------- 删除 --------------------
    def delete_episodic(self, org_id: str, project_id: str, episodic_id: str) -> None:
        payload = {"org_id": org_id, "project_id": project_id, "episodic_id": episodic_id}
        self._post(f"{self.base_url}/api/v2/memories/episodic/delete", payload)

    def delete_semantic(self, org_id: str, project_id: str, semantic_id: str) -> None:
        payload = {"org_id": org_id, "project_id": project_id, "semantic_id": semantic_id}
        self._post(f"{self.base_url}/api/v2/memories/semantic/delete", payload)

# ==========================================
# Part B: FastAPI Web 接口层
# ==========================================

from starlette.responses import JSONResponse, Response

app = FastAPI(title="Memory Server")

# 初始化业务逻辑单例
memory_server = MemoryServer()

def _to_fastapi_response(r):
    """将 requests.Response 安全地转换为 FastAPI 可返回对象。"""
    # 已是可 JSON 序列化的，直接返回
    if isinstance(r, (dict, list, str, int, float, bool)) or r is None:
        return r
    # requests.Response
    status_code = getattr(r, "status_code", None)
    if status_code is not None:
        try:
            data = r.json()
            return JSONResponse(status_code=status_code, content=data)
        except ValueError:
            # 非 JSON 响应
            text = getattr(r, "text", "")
            return Response(status_code=status_code, content=text)
    return r


# 运行与健康
@app.get("/v1/health")
def health():
    return _to_fastapi_response(memory_server.health())

# 项目管理
@app.post("/v1/project/create")
def create_project(org_id: str = 'default_org_id', project_id: str = 'default_project_id', description: str = "", embedder: str = "", reranker: str = ""):
    return _to_fastapi_response(memory_server.create_project(org_id, project_id, description, embedder, reranker))

@app.post("/v1/projects/get")
def get_project(org_id: str = 'default_org_id', project_id: str = 'default_project_id'):
    return _to_fastapi_response(memory_server.get_project(org_id, project_id))

@app.post("/v1/projects/delete", status_code=204)
def delete_project(org_id: str = 'default_org_id', project_id: str = 'default_project_id'):
    memory_server.delete_project(org_id, project_id)

# 记忆添加
@app.post("/v1/memories/add")
def add_memories(messages: List[Dict[str, Any]], org_id: str = 'default_org_id', project_id: str = 'default_project_id'):
    return memory_server.add_memories(org_id, project_id, messages)

# 检索
@app.post("/v1/memories/search")
def search_memories(query: str, org_id: str = 'default_org_id', project_id: str = 'default_project_id', top_k: int = 10, filter: str = "", types: Optional[List[str]] = None):
    return memory_server.search_memories(org_id, project_id, query, top_k=top_k, filter=filter, types=types)

# 列表
@app.post("/v1/memories/list")
def list_memories(org_id: str = 'default_org_id', project_id: str = 'default_project_id', page_size: int = 100, page_num: int = 0, filter: str = "", type_: str = "episodic"):
    return memory_server.list_memories(org_id, project_id, page_size, page_num, filter, type_)

# 删除
@app.post("/v1/memories/episodic/delete", status_code=204)
def delete_episodic(episodic_id: str, org_id: str = 'default_org_id', project_id: str = 'default_project_id'):
    memory_server.delete_episodic(org_id, project_id, episodic_id)

@app.post("/v1/memories/semantic/delete", status_code=204)
def delete_semantic(semantic_id: str, org_id: str = 'default_org_id', project_id: str = 'default_project_id'):
    memory_server.delete_semantic(org_id, project_id, semantic_id)

if __name__ == "__main__":
    # 启动服务，监听 8225 端口
    print("FastAPI 服务正在启动...")
    uvicorn.run(app, host="0.0.0.0", port=8225)