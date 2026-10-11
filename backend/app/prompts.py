"""Prompt templates (LangChain) for the generative LLM players.

The system prompt is static so it can sit in front of a Bedrock cache point;
everything that changes per move goes in the user message.
"""

from langchain_core.prompts import PromptTemplate

SYSTEM_PROMPT = (
    "You are a chess engine playing an automated game. "
    "Each turn you get the position and a numbered list of every legal move. "
    "Choose the strongest move: deliver checkmate if available, otherwise win material safely, "
    "avoid leaving pieces undefended, and improve your position. "
    "Answer with the number of your chosen move on a final line in the form: MOVE: <number>. "
    "Keep any reasoning to one short sentence, or skip it."
)

# The format rule is repeated last so it is the freshest instruction when the model answers.
USER_TEMPLATE = PromptTemplate.from_template(
    "{position}{feedback}\n\nEnd your reply with: MOVE: <number>"
)


def build_user_prompt(position_text: str, feedback: str | None) -> str:
    fb = f"\n\n(Previous reply was invalid: {feedback}. Answer with a single number from the list.)" if feedback else ""
    return USER_TEMPLATE.format(position=position_text, feedback=fb)
