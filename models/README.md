# models/

This folder holds all local model files and grammar definitions used by The Yuki Project.

**Git policy**: `.gguf`, `.bin`, and `.safetensors` files are excluded by `.gitignore`.
Only the folder structure, grammar files, and this README are tracked.

---

## Folder Structure

```
models/
├── chat/          ← Main chat/instruct GGUF (used for all LLM calls)
├── embeddings/    ← Embedding GGUF (optional — replaces sentence-transformers)
├── draft/         ← Draft GGUF for speculative decoding (optional)
└── grammars/      ← BNF grammar files (tracked in git)
    ├── json.gbnf              Generic JSON grammar
    ├── json_reflection.gbnf   Reflection payload schema
    └── json_extraction.gbnf   Fact/entity/relationship extraction schema
```

---

## Choosing a Model

The Yuki Project works with any GGUF in chat/instruct format.
Recommended minimums for reliable reflection (trait/emotion growth):

| Size | Quality | Notes |
|------|---------|-------|
| 4B Q4 | Marginal — reflection JSON often incomplete | Current default with llama-server |
| 7–8B Q4 | Good — consistent structured output | Recommended minimum |
| 13B Q4 | Very good — nuanced deltas | Ideal if VRAM allows |

Good starting points (download from Hugging Face):
- `bartowski/Mistral-7B-Instruct-v0.3-GGUF`
- `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF`
- `bartowski/gemma-2-9b-it-GGUF`

Drop the `.gguf` file into `models/chat/`.

---

## Embedding Model (optional)

Used for in-process vector generation — faster than sentence-transformers over HTTP.
Drop into `models/embeddings/`.

Recommended:
- `nomic-ai/nomic-embed-text-v1.5-GGUF` (nomic-embed-text-v1.5.Q4_K_M.gguf)
- `mixedbread-ai/mxbai-embed-large-v1-GGUF`

---

## Draft Model for Speculative Decoding (optional)

Must be from the same model family as the chat model.
Drop into `models/draft/`.

Example pair:
- Chat:  `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`
- Draft: `Meta-Llama-3.2-1B-Instruct-Q4_K_M.gguf`

---

## Environment Variables

Set these before starting The Yuki Project to activate the in-process backend.
If `LLAMA_CPP_MODEL` is **not set**, The Yuki Project uses the existing HTTP llama-server on port 8080 — no change.

```bash
# Required to activate llama-cpp-python backend
LLAMA_CPP_MODEL=models/chat/your-model.gguf

# Optional — in-process embeddings (falls back to sentence-transformers if unset)
LLAMA_CPP_EMBED_MODEL=models/embeddings/your-embed-model.gguf

# Optional — speculative decoding
LLAMA_CPP_DRAFT_MODEL=models/draft/your-draft-model.gguf

# Context window (default: 4096)
LLAMA_CPP_N_CTX=8192

# GPU layers to offload (-1 = all, 0 = CPU only)
LLAMA_CPP_N_GPU_LAYERS=35

# Inference threads (default: CPU count)
LLAMA_CPP_N_THREADS=8
```

---

## Installing llama-cpp-python

**CPU only:**
```bash
pip install llama-cpp-python
```

**NVIDIA CUDA:**
```bash
$env:CMAKE_ARGS="-DGGML_CUDA=on"
pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir
```

**AMD ROCm:**
```bash
$env:CMAKE_ARGS="-DGGML_HIPBLAS=on"
pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir
```

**Apple Metal:**
```bash
CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python --upgrade --force-reinstall
```

After installing, verify with:
```bash
python -c "from llama_cpp import Llama; print('llama-cpp-python OK')"
```
