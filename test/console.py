import torch
print("CUDA:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    print("Compute Capability:", torch.cuda.get_device_capability(0))
    print("CUDA ver:", torch.version.cuda)
    print("PyTorch ver:", torch.__version__)
try:
    import vllm
    print("vLLM ver:", vllm.__version__)
except ImportError:
    print("vLLM: NOT installed")
