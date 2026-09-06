from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser


class MomoRes(BaseModel):
    mood: str = Field("普通", description="当前的心情")
    text: str = Field("。。。", description="回答的文字")


def get_output_parser():
    outputParser = PydanticOutputParser(pydantic_object=MomoRes)
    return outputParser
