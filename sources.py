"""Curated-deep source lists for the research crawl.

Two focus areas, both feeding active WPAI work:
  * local-inference  — running large models on the 6GB-VRAM box (feeds the Recurrsive campaign
                       and the 14B-is-slow bottleneck in the discovery engine)
  * open-endedness   — novelty search / quality-diversity / program synthesis / symbolic
                       regression (feeds the greedy-vs-novelty discovery experiment)

Each repo/query is hand-picked for signal, not scraped by star-count. Adding a token later lets
`crawl.py` enrich these with GitHub-search expansion, but the curated core stands on its own.
"""

# (owner/repo, short-why) — README pulled from raw.githubusercontent (no API rate limit).
GITHUB_REPOS = {
    "local-inference": [
        ("ggml-org/llama.cpp", "the reference CPU/GPU-offload local inference runtime"),
        ("ggml-org/ggml", "the tensor library under llama.cpp; GGUF + quant kernels"),
        ("ollama/ollama", "the local model runner WPAI already uses (ollama-engine)"),
        ("turboderp-org/exllamav2", "fast quantized (EXL2) inference on consumer GPUs"),
        ("vllm-project/vllm", "paged-attention serving; KV-cache management reference"),
        ("sgl-project/sglang", "structured generation + fast serving runtime"),
        ("InternLM/lmdeploy", "quantized serving toolkit (AWQ/KV-int)"),
        ("ModelTC/lightllm", "lightweight high-throughput LLM serving"),
        ("PygmalionAI/aphrodite-engine", "consumer-focused high-throughput serving"),
        ("huggingface/text-generation-inference", "HF production inference server"),
        ("microsoft/DeepSpeed", "MoE + ZeRO-offload; the offload playbook"),
        ("FMInference/FlexLLMGen", "high-throughput generative inference on ONE GPU (offload) — Recurrsive-core"),
        ("SJTU-IPADS/PowerInfer", "CPU/GPU hybrid local inference exploiting activation sparsity — Recurrsive-core"),
        ("kvcache-ai/ktransformers", "MoE expert offload to run big MoE on tiny VRAM — directly the 6GB story"),
        ("mit-han-lab/streaming-llm", "attention sinks for streaming / long-context at fixed cost"),
        ("Dao-AILab/flash-attention", "the fused attention kernel everything builds on"),
        ("state-spaces/mamba", "selective state-space model (SSM) reference"),
        ("johnma2006/mamba-minimal", "minimal readable Mamba — study implementation"),
        ("state-spaces/s4", "structured state spaces; the SSM lineage"),
        ("HazyResearch/zoology", "MQAR associative-recall benchmark Recurrsive validated against"),
        ("AutoGPTQ/AutoGPTQ", "GPTQ post-training quantization toolkit"),
        ("casper-hansen/AutoAWQ", "AWQ 4-bit quantization"),
        ("mit-han-lab/llm-awq", "activation-aware weight quantization (AWQ) source"),
        ("microsoft/BitNet", "1-bit / ternary LLM inference framework"),
        ("unslothai/unsloth", "memory-efficient finetune + inference kernels"),
        ("linkedin/Liger-Kernel", "fused Triton kernels for throughput/memory"),
        ("b4rtaz/distributed-llama", "shard a big model across weak devices"),
        ("mit-han-lab/smoothquant", "W8A8 quantization by activation smoothing"),
        ("huggingface/optimum-quanto", "flexible PyTorch quantization backend"),
        ("triton-lang/triton", "the GPU kernel language for custom dequant-GEMV (Recurrsive next step)"),
    ],
    "open-endedness": [
        ("google-deepmind/funsearch", "LLM + evolutionary search that made real math discoveries — closest prior art to our experiment"),
        ("CarperAI/OpenELM", "LLMs as mutation operators inside MAP-Elites; open-ended code evolution"),
        ("adaptive-intelligent-robotics/QDax", "quality-diversity / MAP-Elites in JAX, at scale"),
        ("resibots/pymap_elites", "the canonical minimal MAP-Elites (Mouret) reference"),
        ("MilesCranmer/PySR", "high-performance symbolic regression — the curve-fitting-to-a-law core of our task"),
        ("MilesCranmer/SymbolicRegression.jl", "the SR search engine under PySR"),
        ("trevorstephens/gplearn", "genetic-programming symbolic regression, sklearn-style"),
        ("SakanaAI/AI-Scientist", "end-to-end LLM-driven scientific discovery loop"),
        ("uber-research/poet", "POET: paired open-ended trailblazer (Wang/Stanley) open-endedness"),
        ("google/evojax", "hardware-accelerated neuroevolution / evolutionary strategies"),
        ("CMA-ES/pycma", "CMA-ES reference — the strong baseline optimizer to beat"),
        ("DEAP/deap", "distributed evolutionary algorithms framework"),
        ("facebookresearch/nevergrad", "gradient-free / evolutionary optimization platform"),
        ("google-deepmind/opro", "optimization by PROmpting — LLM as optimizer"),
        ("conceptofmind/PaLM", "reference; skip if noisy"),  # low priority; kept for breadth
    ],
}

# (query, max_results) — arXiv Atom API (no auth, be polite). Abstracts are clean text = high signal.
ARXIV_QUERIES = {
    "local-inference": [
        ("mixture of experts inference offloading consumer GPU", 8),
        ("post-training quantization large language models GPTQ AWQ", 8),
        ("Mamba selective state space model language", 6),
        ("speculative decoding large language model acceleration", 6),
        ("high throughput generative inference single GPU offloading", 6),
        ("KV cache compression long context inference", 6),
        ("1-bit ternary quantization large language model", 5),
        ("associative recall state space model attention hybrid", 5),
    ],
    "open-endedness": [
        ("novelty search open-ended evolutionary computation", 7),
        ("MAP-Elites quality diversity illuminating search space", 7),
        ("large language models mathematical discovery evolutionary FunSearch", 6),
        ("symbolic regression discovering equations from data", 7),
        ("large language model scientific hypothesis discovery", 6),
        ("quality diversity optimization robotics", 5),
        ("abduction inference to the best explanation machine learning", 5),
    ],
}

# Human-facing focus descriptions (embedded in each seed's header for retrieval context).
FOCUS_BLURB = {
    "local-inference": "Running large models locally on 6GB VRAM + host RAM (MoE/INT4/SSM/offload).",
    "open-endedness": "Novelty search, quality-diversity, program synthesis, symbolic regression.",
}
