"""
api_gateway.py

使用 FastAPI 暴露一个“上层封装”的 HTTP 接口，内部通过 MemServer 调用 memmachine-server 的 API v2。

目标：
- 对外提供更易用的 JSON 契约（可直接传 user_id/agent_id/session_id）
- 统一将业务侧的 user_id/agent_id/session_id 注入到 messages[*].metadata 中
- 提供内置过滤（根据 user_id/agent_id/session_id 组合生成 filter，并与自定义 filter 合并）

运行：
  export MEMORY_BACKEND_URL=http://localhost:8080  # memmachine-server 地址
  uvicorn api_gateway:app --host 0.0.0.0 --port 8090 --reload

示例：
- 添加记忆（上层接口）：
  POST http://localhost:8090/v1/memories/add
  {
    "org_id": "org",
    "project_id": "proj",
    "user_id": "u1",
    "agent_id": "a1",
    "session_id": "s1",
    "messages": [ {"role":"user", "content":"我喜欢 Python"} ]
  }
  内部会转换为 memmachine 的 /api/v2/memories 所需格式。

- 搜索记忆：
  POST http://localhost:8090/v1/memories/search
  {
    "org_id": "org",
    "project_id": "proj",
    "query": "喜欢",
    "top_k": 10,
    "user_id": "u1"  # 可选，将合并为 filter: metadata.user_id='u1'
  }
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Literal

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from memServer import MemServer


# -------------------- Pydantic 模型 --------------------
class ProjectConfigIn(BaseModel):
    embedder: str = ""
    reranker: str = ""


class CreateProjectIn(BaseModel):
    org_id: str
    project_id: str
    description: str = ""
    config: ProjectConfigIn = Field(default_factory=ProjectConfigIn)


class GetOrDeleteProjectIn(BaseModel):
    org_id: str
    project_id: str


class MemoryMessageIn(BaseModel):
    role: str = "user"  # user/assistant/system
    content: str
    metadata: Dict[str, str] = Field(default_factory=dict)


class AddMemoriesIn(BaseModel):
    org_id: str
    project_id: str
    # 上层支持把业务会话维度放在顶层
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    messages: List[MemoryMessageIn]


class SearchMemoriesIn(BaseModel):
    org_id: str
    project_id: str
    query: str
    top_k: int = 10
    # 内置过滤维度（可选）
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    # 额外自定义 filter 字符串，可与内置合并
    filter: str = ""
    types: Optional[List[Literal["episodic", "semantic"]]] = None


class ListMemoriesIn(BaseModel):
    org_id: str
    project_id: str
    page_size: int = 100
    page_num: int = 0
    type: Literal["episodic", "semantic"] = "episodic"
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    filter: str = ""


class DeleteEpisodicIn(BaseModel):
    org_id: str
    project_id: str
    episodic_id: str


class DeleteSemanticIn(BaseModel):
    org_id: str
    project_id: str
    semantic_id: str


# -------------------- 工具函数 --------------------
def _merge_metadata(defaults: Dict[str, str], existing: Dict[str, str]) -> Dict[str, str]:
    # 以 existing 为主，补充 defaults
    merged = dict(defaults)
    merged.update({k: v for k, v in (existing or {}).items() if v is not None})
    # 仅保留字符串
    return {k: str(v) for k, v in merged.items() if v is not None}


def _role_to_producer(role: str) -> str:
    # 简单映射：assistant -> assistant，其余 -> user
    return "assistant" if (role or "").lower() == "assistant" else "user"


def _build_filter(user_id: Optional[str], agent_id: Optional[str], session_id: Optional[str], extra: str) -> str:
    parts: List[str] = []
    if user_id:
        parts.append(f"metadata.user_id='{user_id}'")
    if agent_id:
        parts.append(f"metadata.agent_id='{agent_id}'")
    if session_id:
        parts.append(f"metadata.session_id='{session_id}'")
    if extra:
        parts.append(f"({extra})")
    return " AND ".join(parts)


# -------------------- FastAPI 应用 --------------------
app = FastAPI(title="MemMachine Gateway", description="A thin HTTP gateway on top of memmachine-server")

BACKEND_URL = os.environ.get("MEMORY_BACKEND_URL", "http://localhost:8080")
api = MemServer(base_url=BACKEND_URL)


# 运行与健康
@app.get("/v1/health")
def health() -> Dict[str, Any]:
    try:
        return api.health()
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# 项目管理
@app.post("/v1/projects")
def create_project(spec: CreateProjectIn) -> Dict[str, Any]:
    try:
        return api.create_project(
            spec.org_id, spec.project_id, description=spec.description,
            embedder=spec.config.embedder, reranker=spec.config.reranker
        )
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/v1/projects/get")
def get_project(spec: GetOrDeleteProjectIn) -> Dict[str, Any]:
    try:
        return api.get_project(spec.org_id, spec.project_id)
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/v1/projects/delete", status_code=204)
def delete_project(spec: GetOrDeleteProjectIn) -> None:
    try:
        api.delete_project(spec.org_id, spec.project_id)
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# 记忆添加
@app.post("/v1/memories/add")
def add_memories(spec: AddMemoriesIn) -> Dict[str, Any]:
    try:
        defaults = {
            "user_id": spec.user_id or "",
            "agent_id": spec.agent_id or "",
            "session_id": spec.session_id or "",
        }
        msgs: List[Dict[str, Any]] = []
        for m in spec.messages:
            msgs.append({
                "content": m.content,
                "producer": _role_to_producer(m.role),
                "role": m.role,
                "metadata": _merge_metadata(defaults, m.metadata or {}),
            })
        uids = api.add_memories(spec.org_id, spec.project_id, msgs)
        return {"results": [{"uid": u} for u in uids]}
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# 检索
@app.post("/v1/memories/search")
def search_memories(spec: SearchMemoriesIn) -> Dict[str, Any]:
    try:
        flt = _build_filter(spec.user_id, spec.agent_id, spec.session_id, spec.filter)
        data = api.search_memories(
            spec.org_id, spec.project_id, query=spec.query, top_k=spec.top_k,
            filter=flt, types=spec.types
        )
        return data
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# 列表
@app.post("/v1/memories/list")
def list_memories(spec: ListMemoriesIn) -> Dict[str, Any]:
    try:
        flt = _build_filter(spec.user_id, spec.agent_id, spec.session_id, spec.filter)
        data = api.list_memories(
            spec.org_id, spec.project_id, page_size=spec.page_size, page_num=spec.page_num,
            filter=flt, type_=spec.type
        )
        return data
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# 删除
@app.post("/v1/memories/episodic/delete", status_code=204)
def delete_episodic(spec: DeleteEpisodicIn) -> None:
    try:
        api.delete_episodic(spec.org_id, spec.project_id, spec.episodic_id)
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/v1/memories/semantic/delete", status_code=204)
def delete_semantic(spec: DeleteSemanticIn) -> None:
    try:
        api.delete_semantic(spec.org_id, spec.project_id, spec.semantic_id)
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

