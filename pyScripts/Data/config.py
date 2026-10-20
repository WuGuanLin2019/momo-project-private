import os

# 获取当前文件所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 拼接出 Data 目录的路径
MEMORY_DIR = os.path.join(BASE_DIR, "Memory")
# 确保目录存在
os.makedirs(MEMORY_DIR, exist_ok=True)

# 最终的 db 路径
DB_PATH = os.path.join(MEMORY_DIR, "momo_memory.db")
FAISS_PATH = os.path.join(MEMORY_DIR, "embeddingDic.faiss")

# 对话原始数据（记忆提取的原材料）存放目录
CONVERSATION_DIR = os.path.join(BASE_DIR, "Conversation")
# 确保目录存在
os.makedirs(CONVERSATION_DIR, exist_ok=True)
