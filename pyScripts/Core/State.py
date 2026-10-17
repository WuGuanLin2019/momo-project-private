from enum import Enum
import threading
from dataclasses import dataclass

from sympy import false

class GenerationState:
    def __init__(self, initGeneration=0):
        self.generation = initGeneration
        self.lock = threading.Lock()

    def add_generation(self):
        with self.lock:
            self.generation += 1
 
    def check_is_current_generation(self, diffGenerationState: "GenerationState | int")->bool:
        with self.lock:
            result = false
            if isinstance(diffGenerationState, GenerationState) :
                result = diffGenerationState.generation == self.generation
            elif isinstance(diffGenerationState,int):
                result = diffGenerationState == self.generation

            if not result:
                print(f"GId不同，中断")
            return result
 


    def update_newest_generation(self, diffGenerationState: "GenerationState"):
        with self.lock:
            diffGenerationState.generation = self.generation
