import argparse
import json
import sys
from pathlib import Path

import fitz
import anthropic

ROOT = Path(__file__).parent
CHUNKS_DIR = ROOT / "data_prep" / "chunks"

sys.path.insert(0, str(ROOT / "data_prep"))
from data_query_tool import TOOLS, execute_tool


def _load_all_chunks() -> str:
    lines = []
    for path in sorted(CHUNKS_DIR.glob("*.json")):
        with open(path) as f:
            chunks = json.load(f)
        for chunk in chunks:
            lines.append(chunk["text"])
    return "\n\n".join(lines)


def _load_plant_pdf() -> str:
    pdf_path = Path(
        "/Users/krishnamavani/Documents/Energy Hackathon"
        "/Plant A (start here)"
        "/(please read first) General information plant A.pdf"
    )
    if not pdf_path.exists():
        return ""
    doc = fitz.open(str(pdf_path))
    return "\n".join(page.get_text() for page in doc).strip()


_PLANT_CHUNKS_TEXT = _load_all_chunks()
_PLANT_PDF_TEXT = _load_plant_pdf()

print(f"[startup] Plant chunks: ~{len(_PLANT_CHUNKS_TEXT)//4:,} tokens")
print(f"[startup] Plant PDF:    ~{len(_PLANT_PDF_TEXT)//4:,} tokens")


def retrieve_handbook(question: str, top_k: int = 5) -> str:
    # RAG teammate: replace this body with your ChromaDB query
    # results = collection.query(query_texts=[question], n_results=top_k)
    # return "\n\n".join(results["documents"][0])
    return ""


BASE_SYSTEM = """You are an expert energy analyst for Plant A, a 1,897 kWp utility-scale solar plant managed by EnerParc.

## Plant structure
- 65 inverters (INV 01.01.001 → INV 01.09.065) across 9 substations
- Each inverter: 5 strings × 24 modules × 255 W = 30.6 kWp
- 5-minute monitoring data from 2017 to June 2026
- Feed-in tariff: typically 11.5 ct/kWh, up to ~40 ct/kWh in market-price periods

## Live tools available
- `query_inverter_errors`       — error counts for a specific inverter
- `compare_inverters_by_errors` — rank all 65 inverters by fault count
- `get_error_timeline`          — monthly/yearly error trend for an inverter
- `get_plant_downtime_events`   — maintenance tickets and incidents

## How to answer
1. Use tools for any precise number or date-specific query — never guess
2. Revenue impact formula:
   energy_lost_kWh = inverter_kWp × hours_down × capacity_factor
   revenue_lost_€  = energy_lost_kWh × tariff_ct_per_kWh / 100
   (use capacity factor 0.15 for 24h periods, 0.35 for daytime-only)
3. Always be specific: inverter ID, date, error code, € amount
4. Make multiple tool calls if needed — thoroughness matters

## Audience
EnerParc operations and asset management staff. Be concise and actionable.
"""


def build_system_prompt(handbook_context: str) -> str:
    parts = [BASE_SYSTEM]
    parts.append("## Plant A documentation\n" + _PLANT_PDF_TEXT)
    parts.append("## Plant A knowledge base\n" + _PLANT_CHUNKS_TEXT)
    if handbook_context.strip():
        parts.append("## Relevant PV engineering reference\n" + handbook_context)
    return "\n\n---\n\n".join(parts)


class PlantAChatbot:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.messages: list[dict] = []

    def chat(self, user_message: str, verbose: bool = False) -> str:
        handbook_ctx = retrieve_handbook(user_message)
        system = build_system_prompt(handbook_ctx)

        self.messages.append({"role": "user", "content": user_message})

        for _ in range(8):
            response = self.client.messages.create(
                model="claude-opus-4-8",
                max_tokens=4096,
                system=system,
                tools=TOOLS,
                messages=self.messages,
                thinking={"type": "adaptive"},
            )

            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                return next((b.text for b in response.content if b.type == "text"), "")

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        if verbose:
                            print(f"  🔧 {block.name}({json.dumps(block.input, separators=(',',':'))})")
                        result = execute_tool(block.name, block.input)
                        if verbose:
                            print(f"     → {result[:200]}{'...' if len(result) > 200 else ''}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                self.messages.append({"role": "user", "content": tool_results})

        return "Reached max reasoning steps. Try a more specific question."

    def reset(self):
        self.messages = []


DEMO_QUESTIONS = [
    "Give me a plant overview — capacity, inverter count, data range.",
    "Which 3 inverters had the most errors in 2023?",
    "What does error code 0A0003 mean?",
    "What were the major outages in 2021 and what did they cost in lost revenue?",
    "Show the error trend for INV 01.09.062 by year.",
]


def run_interactive():
    bot = PlantAChatbot()
    print("\n🌞 Plant A Energy Chatbot  (type 'reset' or 'quit')\n")
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break
        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "reset":
            bot.reset()
            print("  [conversation reset]\n")
            continue
        answer = bot.chat(user_input, verbose=True)
        print(f"\nAssistant: {answer}\n")


def run_demo():
    bot = PlantAChatbot()
    print("\n🌞 Plant A Chatbot — Demo\n" + "=" * 60)
    for i, q in enumerate(DEMO_QUESTIONS, 1):
        print(f"\n[Q{i}] {q}\n" + "-" * 50)
        answer = bot.chat(q, verbose=True)
        print(f"\n{answer}\n")
        bot.reset()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    run_demo() if args.demo else run_interactive()
