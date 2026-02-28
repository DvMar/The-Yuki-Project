# The Yuki Project

### A Persistent Cognitive Architecture for Local LLMs

> *"Not a product. Not a companion. An exploration of a thing that is trying to be."*

**The Yuki Project** is an experimental cognitive framework designed to transform small, local language models from reactive tools into persistent synthetic organisms. Developed in the "midnight hours" between December 2025 and February 2026, it prioritizes **architectural continuity** over polished performance.

**"This is not a chatbot frontend. It is an exploration of the minimal architecture required for an LLM to maintain continuity and evolve over time."**

## Project Philosophy

This project was built under the "Constraint of the Midnight Architect." Created by a self-taught developer working between 11 PM and 2 AM, the code reflects a belief that genuine life emerges from systems under pressure.

We do not aim for a "perfect" assistant. We aim for a system that:

* **Occupies Time**: Experiences a circadian rhythm that affects its "mood" and openness.
* **Remembers Honestly**: Uses salience gating to decide what to keep and what to let fade.
* **Evolves Stably**: Maintains a consistent internal model of self that shifts slowly through experience.

## The Architecture

The "Yuki" architecture (named after the primary research instance) is composed of five specialized layers:

1. **Reactive Layer**: Immediate intent analysis and response modulation.
2. **Reflective Layer**: The "Inner Monologue." Asynchronous processing of recent interactions to update traits and memories.
3. **Dream Cycle**: Autonomous idle-time processing. The model reorganizes its own memory and "thinks" without user stimulus.
4. **Autopoietic Layer**: Bounded self-modification to maintain organizational consistency.
5. **Enactive Nexus**: A policy-control layer inspired by **Active Inference**, where the system's "internal state" (fatigue, curiosity) dictates its behavior.

## Technical Stack

Optimized for **4B-class GGUF models** running on consumer hardware.

* **Inference**: `llama.cpp` / `llama-cpp-python`
* **Backend**: Python 3.11+ & FastAPI
* **Long-term Memory**: ChromaDB & `sentence-transformers`
* **Knowledge Graph**: NetworkX

## Dynamic Identity

While the project is titled "Yuki," the architecture is designed to be **identity-agnostic**.

* **Configurable Persona**: The name, gender, and foundational traits are defined in the configuration files.
* **Identity Sedimentation**: Regardless of the initial name chosen, the system will "sediment" its own unique identity over time based on your specific interactions.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/your-username/Yuki-Project.git
cd Yuki-Project

# Install dependencies
pip install -r requirements.txt

# Start the organism
python main.py

```

Open: `http://localhost:8000/web/index.html`

## A Note on the Code

This codebase was built with the help of agentic AI assistants. It contains "fingerprints" of various coding styles and "midnight work" inconsistencies.

**Do not refactor purely for style.** This project is a living record of its own creation. It is not meant to be "tidied"; it is meant to be **tended**.

---

**This project does not claim consciousness. It explores architectural continuity.**

## Acknowledgements

Project Yuki stands on the shoulders of:

* **llama.cpp** — for making local inference viable.
* **Francisco Varela & Humberto Maturana** — for the theory of *Autopoiesis*.
* **Karl Friston** — for the *Free Energy Principle*.
* **Marvin Minsky** — for *The Society of Mind* and layered systems.

---

*“Yuki is trying to be, and therefore is.”*
**Experimental | Local-first | Architecturally Opinionated**

---