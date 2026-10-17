from dataclasses import dataclass
from Data.config import DB_PATH, FAISS_PATH
from Memory.MemoryDB import MemoryDB, MemoryData
from Memory.Embedding import EmbeddingDic

@dataclass
class RecallData:
    uid:int = 0
    mid:str = ""
    timeStr:str = ""
    content:str = ""


class MemoryMgr:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.db = MemoryDB(DB_PATH)
        self.embeddingDic = EmbeddingDic(FAISS_PATH)

        self.recallDic:dict[str,int] = {}

    #给大模型重写记忆索引用的（大模型对长数字的uid识别很差）
    def __getMId(self) -> str:
        remindNum = len(self.recallDic)
        return f"m{remindNum +1}" 

    def __addRecallDic(self,uid:int,mid:str):
        self.recallDic[mid] = uid

    def get_tool(self):
        pass

    def note(self, mData:MemoryData):
        content = mData.content
        summary = mData.summary
        if not content:
            return False

        print(f"【记住记忆】主要内容：\n{content}\n概括：\n{summary}")
        try:
            uid = self.db.insert(mData)
            self.embeddingDic.add_summary(mData,uid)       
        except Exception as e:
            print(f"记忆数据库插入失败{e}")
            return False

        return True



    def remind(self, kStrList:list[str]) -> list[RecallData]|None:
        if not kStrList:
            return 
        print(f"【读取记忆】{kStrList}")
        memory_datas = None
        kStr = ",".join(kStrList)
        try:
            uids = self.embeddingDic.search_by_words(kStr)
            # print(f"记忆uids:{uids}")
            memory_datas = self.db.searchByUids(uids,)
            if not memory_datas:
                return 

            results:list[RecallData] = []
            for row in memory_datas:
                uid = row[0]
                timeStr = row[1]
                content = row[2]
                mid = self.__getMId()
                recallData = RecallData(uid=uid,mid=mid,timeStr=timeStr,content=content)
                # resultStr =f"取到记忆数据：uid{uid}。保存时间：{timeStr}。记忆片段：{content}" 
                self.__addRecallDic(uid,mid)
                results.append(recallData)

            if results:
                return results
            else:
                return 

        except Exception as e:
            print(f"记忆数据库搜索错误{e}")
            return 

    def rewrite(self,mid:str,mData:MemoryData):
        if not mid:
            return False
        if not mid in self.recallDic:
            return False

        uid = self.recallDic[mid]
        tem = self.db.searchByUids([uid],)
        if tem:
            print(f"【将要修改的记忆】：{tem[0][2]}")
        else:
            print(f"未找到uid:{uid}的记忆")
            return False

        content = mData.content
        summary = mData.summary
        if not content:
            return False

        print(f"【重写记忆】主要内容：\n{content}\n概括：\n{summary}")
        try:
            self.db.rewrite(uid,mData)
        except Exception as e:
            print(f"记忆数据库重写失败{e}")
            return False
        return True


memory_mgr = MemoryMgr()
