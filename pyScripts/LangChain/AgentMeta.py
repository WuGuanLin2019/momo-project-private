from dataclasses import dataclass

from Core.Input.InputDataMgr import InputData


@dataclass
class AgentMetaContext:
    agent_name: str = "None"
    input_data: InputData = None
