
from queue import Empty, Queue
from Brain.Emotion.EmotionMgr import emotion_update
from LangChain.Generate import think
from Core.State import GenerationState, SpeakTask
from Brain.conversation import add_to_conversation, get_full_conversation,input_data


def brain_loop(input_text_queue:Queue, to_speak_queue:Queue, pipelineState: GenerationState):
    generate_state = GenerationState()

    def add_to_speak_queue(str:str):
        if str.strip() != "":
            task = SpeakTask(generate_state.generation,str)
            to_speak_queue.put(task)

    def add_to_input_queue(data:input_data):
        if data.content.strip() != "":
            input_text_queue.put(data)


    while True:
        emotion_update()

        try:
            inputData = input_text_queue.get(timeout = 1)
        except Empty:
            print(".",end="")
            continue

        if not inputData:
            continue
        pipelineState.update_newest_generation(generate_state)

        add_to_conversation(inputData)
        
        # input_str = get_full_conversation()
        # think(input_str, add_to_speak_queue,add_to_input_queue, generate_state, pipelineState)
        
        think(inputData.content, add_to_speak_queue, generate_state, pipelineState)

