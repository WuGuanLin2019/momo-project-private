from dataclasses import dataclass, field

from Core.Input.InputDataMgr import InputData


@dataclass
class AgentMetaContext:
    agent_name: str = "None"
    input_data: InputData = field(default_factory=InputData)
