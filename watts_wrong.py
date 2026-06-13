"""
Watt's Wrong O&M Assistant - Decision engine for solar plant maintenance.

Single agent that calls 3 tools (revenue, risk, crew) then synthesizes results
into maintenance decisions: do_nothing / monitor / act.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic

# Add data_prep to path for tools
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "data_prep"))
from data_query_tool import analyze_revenue, score_risk, check_crew


class WattsWrongAgent:
    """O&M decision agent that analyzes zones and recommends actions."""

    def __init__(self):
        self.client = anthropic.Anthropic()

    def analyze_zone(self, zone_id: str, start_date: str, end_date: str) -> dict:
        """
        Main entry point: analyze zone and return maintenance decision.
        Always runs all 3 tools, then synthesizes into verdict.
        """
        print(f"🔍 Analyzing zone {zone_id} ({start_date} to {end_date})")

        # Step 1: Execute all 3 tools (the "three perspectives")
        print("  📊 Running revenue analysis...")
        revenue_result = analyze_revenue(zone_id, start_date, end_date)

        print("  ⚡ Running risk assessment...")
        risk_result = score_risk(zone_id, start_date, end_date)

        print("  👷 Checking crew availability...")
        crew_result = check_crew(start_date, end_date)

        # Step 2: Agent synthesis (single LLM call)
        print("  🧠 Synthesizing decision...")
        verdict = self._agent_synthesize(zone_id, revenue_result, risk_result, crew_result)

        return {
            "zone_id": zone_id,
            "analysis_period": f"{start_date} to {end_date}",
            "tool_results": {
                "revenue": revenue_result,
                "risk": risk_result,
                "crew": crew_result
            },
            "verdict": verdict,
            "timestamp": datetime.now().isoformat()
        }

    def _agent_synthesize(self, zone_id: str, revenue: dict, risk: dict, crew: dict) -> dict:
        """
        Single LLM call that synthesizes all 3 tool results into final verdict.
        Must cite actual numbers from tools and note any tensions.
        """

        system_prompt = """You are Watt's Wrong, an expert O&M assistant for Plant A solar facility.

You have received results from 3 analysis tools for a zone. Make a maintenance decision based on ALL THREE perspectives:

DECISION RULES:
- Decision must be: "do_nothing", "monitor", or "act"
- ALWAYS cite actual numbers from the tool results
- Note any tension between tools (e.g., "revenue says urgent, crew unavailable until Tuesday")
- If decision is "act", draft a service ticket with fields: component, startdate, enddate, category

REASONING FRAMEWORK:
- Revenue: Financial urgency (€ losses, weekly run-rate)
- Risk: Technical severity (error codes, safety implications)
- Crew: Operational feasibility (availability, scheduling constraints)

Return JSON with exact structure:
{
  "decision": "do_nothing" | "monitor" | "act",
  "severity": <risk_score_0_100>,
  "euro_loss": <total_euro_loss>,
  "reasoning": "<explanation citing specific numbers>",
  "dissent_note": "<any tension between perspectives>",
  "draft_ticket": {<ticket_fields>} // only if decision=="act"
}
"""

        user_message = f"""Zone: {zone_id}

REVENUE ANALYSIS:
{json.dumps(revenue, indent=2)}

RISK ASSESSMENT:
{json.dumps(risk, indent=2)}

CREW AVAILABILITY:
{json.dumps(crew, indent=2)}

Make your O&M decision. Every number must come from these tool results."""

        try:
            response = self.client.messages.create(
                model="claude-opus-4-8",
                max_tokens=1000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )

            # Extract the text content from response
            text_content = ""
            for block in response.content:
                if block.type == "text":
                    text_content += block.text

            # Parse JSON from response
            try:
                verdict = json.loads(text_content)
                return verdict
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return {
                    "decision": "monitor",
                    "severity": risk.get("severity_0_100", 0),
                    "euro_loss": revenue.get("euro_loss", 0),
                    "reasoning": f"Analysis completed but synthesis failed. Raw response: {text_content}",
                    "dissent_note": "Unable to parse structured response",
                    "error": "JSON parsing failed"
                }

        except Exception as e:
            return {
                "decision": "monitor",
                "severity": risk.get("severity_0_100", 0),
                "euro_loss": revenue.get("euro_loss", 0),
                "reasoning": f"Synthesis failed due to API error: {str(e)}",
                "dissent_note": "Tool results available but agent synthesis failed",
                "error": str(e)
            }


def demo_analysis():
    """Demo the O&M assistant with a sample zone analysis."""

    agent = WattsWrongAgent()

    # Demo scenario: Analyze zone A.019 for the last week
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)

    print("🌞 Watt's Wrong O&M Assistant Demo")
    print("=" * 50)

    result = agent.analyze_zone(
        zone_id="A.019",
        start_date=str(start_date),
        end_date=str(end_date)
    )

    print("\n📋 ANALYSIS RESULTS:")
    print(f"Zone: {result['zone_id']}")
    print(f"Period: {result['analysis_period']}")

    print(f"\n💰 REVENUE IMPACT: {result['tool_results']['revenue']['trace']}")
    print(f"⚡ RISK ASSESSMENT: {result['tool_results']['risk']['trace']}")
    print(f"👷 CREW STATUS: {result['tool_results']['crew']['trace']}")

    verdict = result['verdict']
    decision_emoji = {"do_nothing": "✅", "monitor": "👀", "act": "🚨"}.get(verdict['decision'], "❓")

    print(f"\n🎯 DECISION: {verdict['decision'].upper()} {decision_emoji}")
    print(f"Severity: {verdict['severity']}/100")
    print(f"Revenue Loss: €{verdict['euro_loss']}")
    print(f"\nReasoning: {verdict['reasoning']}")

    if verdict.get('dissent_note'):
        print(f"⚠️  Tension: {verdict['dissent_note']}")

    if verdict.get('draft_ticket'):
        print(f"\n📋 DRAFT SERVICE TICKET:")
        print(json.dumps(verdict['draft_ticket'], indent=2))

    print(f"\n✅ Analysis completed at {result['timestamp']}")


if __name__ == "__main__":
    demo_analysis()