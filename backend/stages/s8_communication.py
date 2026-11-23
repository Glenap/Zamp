"""Draft only; transport is a separate explicit action."""

from backend.llm import draft_messages
from .common import result


def run(context):
    messages = draft_messages(context["form"], context["decision"], context["settings"])["messages"]
    context["messages"] = messages
    return result("Messages drafted; nothing sent.", data={"messages": messages})
