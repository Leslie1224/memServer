import openai
from openai import OpenAI

# 配置参数
BASE_URL = "http://192.168.1.86:8899/v1"
API_KEY = "gpustack_a344bdf5295e3921_6c68ea9d0610480dbd7ee5d5c76895ec"

# 初始化客户端
client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY
)

def test_chat_model(model_name):
    print(f"\n--- 测试对话模型: {model_name} ---")
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "你是一个有帮助的助手。"},
                {"role": "user", "content": "你好，请简洁地自我介绍一下。"}
            ],
            max_tokens=100,
            temperature=0.7
        )
        content = response.choices[0].message.content
        print(f"回答成功：\n{content}")
    except Exception as e:
        print(f"测试失败 [{model_name}]: {e}")

def test_embedding_model(model_name):
    print(f"\n--- 测试向量模型: {model_name} ---")
    try:
        response = client.embeddings.create(
            model=model_name,
            input="这是一条用于测试向量生成的文本。"
        )
        embedding = response.data[0].embedding
        print(f"向量生成成功！维度: {len(embedding)}")
        print(f"前5位数据: {embedding[:5]}")
    except Exception as e:
        print(f"测试失败 [{model_name}]: {e}")

if __name__ == "__main__":
    # 1. 测试 Qwen 对话模型
    chat_models = ["Qwen3-1.7b", "Qwen3-8B"]
    for model in chat_models:
        test_chat_model(model)

    # 2. 测试 BGE 向量模型
    embedding_models = ["bge-large-zh-v1.5"]
    for model in embedding_models:
        test_embedding_model(model)