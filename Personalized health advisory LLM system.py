# ==============================================================================
# Personalized Health Advisory LLM System
# Implements the described RAG and structured prompt pipeline using the
# open-source Kimi-KK model, BM25 + monoT5 re-ranking, evidence weighting,
# and a three-stage constrained chain-of-thought for longevity-focused advice.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Iterable, Tuple
import heapq
import math
import re

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # Fallback minimal BM25 if rank_bm25 is unavailable
    BM25Okapi = None

try:
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    import torch
except ImportError:
    AutoTokenizer = None
    AutoModelForSeq2SeqLM = None
    torch = None

# 1. Data Structures -----------------------------------------------------------

@dataclass
class EvidenceFragment:
    fragment_id: str
    text: str
    doi: str
    pmid: str
    pub_year: int
    study_design: str
    evidence_level: str  # hierarchy label
    journal_impact: float
    disease_category: str
    modifiable_trait: str


# 2. Knowledge Base: BM25 Retrieval + monoT5 Re-ranking -----------------------

class KnowledgeBase:
    def __init__(self, fragments: List[EvidenceFragment]):
        self.fragments = fragments
        corpus = [self._tokenize(f.text) for f in fragments]
        if BM25Okapi is None:
            self.bm25 = None
        else:
            self.bm25 = BM25Okapi(corpus)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def lexical_retrieve(self, query_terms: Iterable[str], top_k: int = 100) -> List[Tuple[EvidenceFragment, float]]:
        tokens = [t.lower() for t in query_terms]
        if self.bm25 is None:
            # Simple TF fallback: count term hits
            scores = []
            for frag in self.fragments:
                frag_tokens = self._tokenize(frag.text)
                score = sum(frag_tokens.count(t) for t in tokens)
                scores.append((frag, float(score)))
            ranked = heapq.nlargest(top_k, scores, key=lambda x: x[1])
            return [(f, s) for f, s in ranked if s > 0]
        scores = self.bm25.get_scores(tokens)
        top_idx = heapq.nlargest(top_k, range(len(scores)), key=scores.__getitem__)
        return [(self.fragments[i], float(scores[i])) for i in top_idx]

    def rerank_monoT5(self, candidates: List[Tuple[EvidenceFragment, float]], query: str, top_k: int = 20) -> List[Tuple[EvidenceFragment, float]]:
        if AutoTokenizer is None or AutoModelForSeq2SeqLM is None or torch is None:
            # If monoT5 unavailable, pass through BM25 scores
            return candidates[:top_k]

        tokenizer = AutoTokenizer.from_pretrained("castorini/monot5-base-msmarco")
        model = AutoModelForSeq2SeqLM.from_pretrained("castorini/monot5-base-msmarco")
        model.eval()

        rescored = []
        for frag, bm25_score in candidates:
            input_text = f"Query: {query} Document: {frag.text} Relevant:"
            inputs = tokenizer.encode(input_text, return_tensors="pt", truncation=True, max_length=512)
            with torch.no_grad():
                output = model.generate(inputs, max_length=2)
            relevance = tokenizer.decode(output[0], skip_special_tokens=True)
            score = 1.0 if relevance.lower().startswith("true") else 0.0
            rescored.append((frag, bm25_score + score))

        rescored.sort(key=lambda x: x[1], reverse=True)
        return rescored[:top_k]

    def weight_fragments(self, reranked: List[Tuple[EvidenceFragment, float]], now_year: int = 2025) -> List[Tuple[EvidenceFragment, float]]:
        weighted = []
        for frag, score in reranked:
            recency = 1.0 + 0.1 * max(0, now_year - frag.pub_year) ** -0.5  # modest recency bonus
            impact = 1.0 + math.log1p(max(frag.journal_impact, 0))
            hierarchy = {
                "meta-analysis": 1.3,
                "randomized": 1.2,
                "prospective cohort": 1.1
            }.get(frag.evidence_level.lower(), 1.0)
            weighted_score = score * recency * impact * hierarchy
            weighted.append((frag, weighted_score))
        weighted.sort(key=lambda x: x[1], reverse=True)
        return weighted


# 3. Query Construction from Modeling Outputs ---------------------------------

def build_query_terms(model_outputs: Dict[str, Any]) -> List[str]:
    terms = []
    terms.extend(model_outputs.get("top_proteins", []))
    terms.extend(model_outputs.get("diseases", []))
    terms.extend(model_outputs.get("modifiable_traits", []))
    return [t for t in terms if t]


# 4. Structured Prompt Architecture -------------------------------------------

SYSTEM_INSTRUCTION = (
    "You are a longevity-focused health advisory agent. Provide evidence-based, "
    "mechanism-aware guidance grounded in retrieved scientific literature. "
    "Adhere to medical safety: avoid unsupported claims; align with public health guidance."
)

def format_fragments(fragments: List[EvidenceFragment]) -> str:
    lines = []
    for f in fragments:
        meta = f"[{f.pub_year}; {f.study_design}; IF={f.journal_impact}; {f.disease_category}; DOI={f.doi}]"
        lines.append(f"- {f.text} {meta}")
    return "\n".join(lines[:10])  # cap to maintain context budget

def build_structured_prompt(individual_info: Dict[str, Any],
                            model_outputs: Dict[str, Any],
                            fragments: List[EvidenceFragment]) -> str:
    evidence_block = format_fragments(fragments)
    causal_outputs = (
        f"Proteins: {model_outputs.get('top_proteins')}\n"
        f"Disease pathways: {model_outputs.get('diseases')}\n"
        f"Modifiable traits: {model_outputs.get('modifiable_traits')}\n"
        f"Health-potential score: {model_outputs.get('health_potential')}\n"
        f"Disease-mediated scores: {model_outputs.get('disease_scores')}\n"
        f"Trait-mediated scores: {model_outputs.get('trait_scores')}\n"
    )
    inquiry_focus = ", ".join(model_outputs.get("modifiable_traits", []))

    return (
        f"{SYSTEM_INSTRUCTION}\n\n"
        "## Individual Profile\n"
        f"{individual_info}\n\n"
        "## Causal Modeling Outputs\n"
        f"{causal_outputs}\n"
        "## Retrieved Evidence (ranked)\n"
        f"{evidence_block}\n\n"
        "## Inquiry Module\n"
        f"Ask concise questions to clarify modifiable traits, prioritizing: {inquiry_focus}.\n\n"
        "## Output Format (three-stage constrained CoT)\n"
        "1) Evidence-summary: 3–5 lines synthesizing key findings with evidence levels/citations.\n"
        "2) Causal-mapping: stepwise alignment of individual pathways (proteins → mediators → outcomes) with the evidence.\n"
        "3) Recommendation-rationale: specific, actionable guidance per disease/trait, each tied to cited evidence and causal path.\n"
        "Include citations inline as [DOI] or [PMID]. Avoid speculation; stay within medical guidance.\n"
    )


# 5. LLM Invocation (Kimi-KK placeholder) --------------------------------------

class KimiKKClient:
    def __init__(self, model_path: str):
        self.model_path = model_path
        # Load local model here if available. Placeholder to avoid heavy init.

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        # Replace with actual generation call to local Kimi-KK.
        return f"[Kimi-KK output placeholder]\n{prompt[:200]}..."


# 6. End-to-end Advisory Pipeline ---------------------------------------------

def generate_personalized_advice(individual_info: Dict[str, Any],
                                 model_outputs: Dict[str, Any],
                                 kb: KnowledgeBase,
                                 kimi_client: KimiKKClient,
                                 top_k: int = 20) -> str:
    query_terms = build_query_terms(model_outputs)
    candidates = kb.lexical_retrieve(query_terms, top_k=top_k * 5)
    reranked = kb.rerank_monoT5(candidates, query=" ".join(query_terms), top_k=top_k)
    weighted = kb.weight_fragments(reranked)
    top_fragments = [frag for frag, _ in weighted[:top_k]]

    prompt = build_structured_prompt(individual_info, model_outputs, top_fragments)
    return kimi_client.generate(prompt)


# 7. Example Usage (commented) -------------------------------------------------
# fragments = [...]  # load 231,996 EvidenceFragment objects from indexed store
# kb = KnowledgeBase(fragments)
# kimi = KimiKKClient(model_path="path/to/kimi-kk")
# individual_info = {"age": 65, "sex": "F", "region": "England"}
# model_outputs = {
#     "top_proteins": ["ProteinA", "ProteinB"],
#     "diseases": ["I25", "E11"],
#     "modifiable_traits": ["diet", "exercise"],
#     "health_potential": 78.5,
#     "disease_scores": {"I25": 0.42, "E11": 0.33},
#     "trait_scores": {"diet": 0.61, "exercise": 0.48}
# }
# advice = generate_personalized_advice(individual_info, model_outputs, kb, kimi, top_k=10)
# print(advice)

# End of Personalized Health Advisory LLM System
