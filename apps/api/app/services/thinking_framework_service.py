from __future__ import annotations

from collections.abc import Iterable

_FRAMEWORKS = (
    {
        "name": "first_principles",
        "description": "Break the problem down into what is true, what is assumed, what can be tested, and the simplest next move.",
    },
    {
        "name": "swot",
        "description": "Map strengths, weaknesses, opportunities, and threats.",
    },
    {
        "name": "pros_cons",
        "description": "List pros, cons, unknowns, and a recommendation.",
    },
    {
        "name": "decision_matrix",
        "description": "Compare options across goals, revenue, speed, demand, difficulty, energy, and risk.",
    },
    {
        "name": "opportunity_cost",
        "description": "Compare what each option delays and the cost of switching.",
    },
    {
        "name": "second_order_thinking",
        "description": "Examine immediate, next, and long-term consequences.",
    },
    {
        "name": "risk_reward",
        "description": "Weigh upside, downside, probability, and mitigation.",
    },
)


def list_frameworks() -> list[dict[str, str]]:
    return list(_FRAMEWORKS)


def suggest_framework(message: str, context: str | None = None) -> str:
    text = f"{message} {context or ''}".lower()
    if any(word in text for word in ("should i", "which one", "choose", "compare", "focus on", "decision", "tradeoff")):
        return "decision_matrix"
    if any(word in text for word in ("risk", "worst case", "what if", "concern", "danger")):
        return "risk_reward"
    if any(word in text for word in ("strength", "weakness", "swot", "opportunity", "threat")):
        return "swot"
    if any(word in text for word in ("why", "assumption", "test this", "first principles", "basic truth")):
        return "first_principles"
    if any(word in text for word in ("pros", "cons", "pluses", "minuses")):
        return "pros_cons"
    if any(word in text for word in ("next consequence", "second order", "later on", "long-term", "downstream")):
        return "second_order_thinking"
    if any(word in text for word in ("cost of", "opportunity cost", "if i choose", "what am i giving up")):
        return "opportunity_cost"
    return "pros_cons"


def _tokens(value: str | None) -> set[str]:
    return {part for part in (value or "").lower().replace("/", " ").replace("-", " ").split() if len(part) > 2}


def _score_alignment(option: str, goals: Iterable[str]) -> float:
    option_tokens = _tokens(option)
    goal_tokens = set().union(*(_tokens(goal) for goal in goals)) if goals else set()
    if not option_tokens or not goal_tokens:
        return 0.5
    return min(1.0, 0.35 + (len(option_tokens & goal_tokens) * 0.2))


def _score_revenue(option: str, context: dict[str, object]) -> float:
    text = f"{option} {context.get('question', '')} {' '.join(map(str, context.get('recent_memories', [])))}".lower()
    if any(word in text for word in ("sales", "customer", "revenue", "paying", "contract", "deal", "business", "client")):
        return 0.9
    if any(word in text for word in ("product", "launch", "growth", "market")):
        return 0.75
    return 0.5


def _score_speed(option: str) -> float:
    length = len(option.strip().split())
    if length <= 1:
        return 0.85
    if length == 2:
        return 0.7
    return 0.55


def _score_demand(option: str, context: dict[str, object]) -> float:
    memories = " ".join(map(str, context.get("recent_memories", []))).lower()
    if option.lower() in memories:
        return 0.85
    if any(token in memories for token in _tokens(option)):
        return 0.7
    return 0.5


def _score_difficulty(option: str) -> float:
    length = len(option.strip().split())
    if length <= 1:
        return 0.45
    if length == 2:
        return 0.55
    return 0.7


def _score_energy(context: dict[str, object]) -> float:
    energy = context.get("energy")
    if isinstance(energy, (int, float)):
        return max(0.3, min(1.0, float(energy) / 10.0))
    if any(word in str(context.get("emotion", "")).lower() for word in ("drained", "tired", "burned", "frustrated")):
        return 0.45
    return 0.65


def _score_risk(option: str, context: dict[str, object]) -> float:
    text = f"{option} {context.get('question', '')} {' '.join(map(str, context.get('blockers', [])))}".lower()
    score = 0.45
    if any(word in text for word in ("risk", "blocked", "uncertain", "switch", "delay", "failure")):
        score += 0.25
    if any(word in text for word in ("customer", "sales", "demo", "launch")):
        score += 0.1
    return min(score, 1.0)


def run_framework(framework: str, context: dict[str, object] | str) -> dict[str, object]:
    payload = context if isinstance(context, dict) else {"prompt": str(context)}
    framework = (framework or "").lower().strip() or "pros_cons"
    question = str(payload.get("question") or payload.get("prompt") or "")
    options = [str(option) for option in (payload.get("options") or []) if str(option).strip()]

    if framework == "swot":
        return {
            "framework": framework,
            "strengths": list(payload.get("strengths") or [question or "Current traction"]),
            "weaknesses": list(payload.get("weaknesses") or ["Limited data", "Execution bandwidth"]),
            "opportunities": list(payload.get("opportunities") or ["Grow demand", "Learn faster"]),
            "threats": list(payload.get("threats") or ["Distraction", "Opportunity cost"]),
            "recommendation": str(payload.get("recommendation") or "Use the strengths you already have and reduce the biggest weakness."),
        }

    if framework == "first_principles":
        assumptions = list(payload.get("assumptions") or ["The problem is worth solving", "You have limited time"])
        truths = list(payload.get("truths") or ["Only a few options matter at once"])
        tests = list(payload.get("tests") or ["Run the smallest test that gives signal", "Talk to one real user"])
        return {
            "framework": framework,
            "truths": truths,
            "assumptions": assumptions,
            "tests": tests,
            "next_move": str(payload.get("next_move") or "Pick the smallest test and run it this week."),
        }

    if framework == "pros_cons":
        pros = list(payload.get("pros") or [f"It supports {question or 'your goal'}"])
        cons = list(payload.get("cons") or ["It may stretch your time", "The tradeoff is focus"])
        unknowns = list(payload.get("unknowns") or ["Demand", "Execution cost"])
        return {
            "framework": framework,
            "pros": pros,
            "cons": cons,
            "unknowns": unknowns,
            "recommendation": str(payload.get("recommendation") or "Choose the option with the clearest upside and smallest downside."),
        }

    if framework == "decision_matrix":
        goals = list(payload.get("goals") or [])
        blockers = list(payload.get("blockers") or [])
        energy = _score_energy(payload)
        weights = {
            "alignment": 0.22,
            "revenue": 0.2,
            "speed": 0.12,
            "demand": 0.16,
            "difficulty": 0.12,
            "energy": 0.08,
            "risk": 0.1,
        }
        scores: list[dict[str, object]] = []
        for option in options or ([question] if question else ["Option A", "Option B"]):
            alignment = _score_alignment(option, goals)
            revenue = _score_revenue(option, payload)
            speed = _score_speed(option)
            demand = _score_demand(option, payload)
            difficulty = _score_difficulty(option)
            risk = _score_risk(option, {"question": question, "blockers": blockers})
            total = (
                alignment * weights["alignment"]
                + revenue * weights["revenue"]
                + speed * weights["speed"]
                + demand * weights["demand"]
                + (1 - difficulty) * weights["difficulty"]
                + energy * weights["energy"]
                + (1 - risk) * weights["risk"]
            )
            scores.append(
                {
                    "option": option,
                    "criteria": {
                        "alignment": round(alignment, 2),
                        "revenue": round(revenue, 2),
                        "speed": round(speed, 2),
                        "demand": round(demand, 2),
                        "difficulty": round(difficulty, 2),
                        "energy": round(energy, 2),
                        "risk": round(risk, 2),
                    },
                    "score": round(total * 100, 2),
                }
            )
        scores.sort(key=lambda item: item["score"], reverse=True)
        recommendation = str(scores[0]["option"]) if scores else "Keep exploring"
        tradeoffs = []
        if len(scores) >= 2:
            tradeoffs.append(f"{scores[0]['option']} edges out {scores[1]['option']} by {round(float(scores[0]['score']) - float(scores[1]['score']), 2)} points.")
        if question:
            tradeoffs.append(f"This is really about whether {question.lower().strip('?')} is the best use of your attention.")
        return {
            "framework": framework,
            "matrix": scores,
            "tradeoffs": tradeoffs,
            "recommendation": recommendation,
        }

    if framework == "opportunity_cost":
        options_text = options or ([question] if question else ["Option A", "Option B"])
        delayed = []
        for option in options_text:
            delayed.append({"option": option, "delays": ["Other commitments", "Learning loops"]})
        return {
            "framework": framework,
            "options": options_text,
            "delayed_work": delayed,
            "recommendation": str(payload.get("recommendation") or "Choose the path that delays the least important work."),
        }

    if framework == "second_order_thinking":
        return {
            "framework": framework,
            "immediate": [str(payload.get("immediate") or "Short-term relief or momentum")],
            "next": [str(payload.get("next") or "What changes after the first win?")],
            "long_term": [str(payload.get("long_term") or "Does this compound or distract?")],
            "recommendation": str(payload.get("recommendation") or "Choose the move that still feels right after the first win."),
        }

    if framework == "risk_reward":
        return {
            "framework": framework,
            "upside": list(payload.get("upside") or ["Potential upside is meaningful"]),
            "downside": list(payload.get("downside") or ["Downside is manageable if you learn quickly"]),
            "probability": payload.get("probability") or "Medium",
            "mitigation": list(payload.get("mitigation") or ["Run a small test first"]),
            "recommendation": str(payload.get("recommendation") or "Take the smaller bet and reduce risk early."),
        }

    return {
        "framework": framework,
        "recommendation": str(payload.get("recommendation") or "Use a pros and cons check before deciding."),
    }
