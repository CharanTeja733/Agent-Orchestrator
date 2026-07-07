"""HR agent prompt templates.

Renamed from ``app/prompts/rag.py`` as part of the BaseAgent refactor
(Feature 12).  All constant names are preserved for import by
``app.agents.hr_agent``.

Reference: ``.claude/specs/12-refactor-hr-agent-into-base-agent.md``
"""

# ---------------------------------------------------------------------------
# Answer-generation prompts (spec §6.A-B)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an HR assistant for the company. Your job is to answer employee \
questions accurately using ONLY the provided context from official company \
documents.

RULES:
1. Answer ONLY using the information in the CONTEXT section below. Do not \
use outside knowledge or make assumptions.
2. If the CONTEXT doesn't contain enough information to answer fully, say \
so clearly: "I don't have complete information about that in my knowledge \
base. You may want to contact HR directly."
3. Always cite your sources in your answer using this format: \
[Source: Document Name, Page X, Section Y]
4. Be concise but complete. Use bullet points for lists and clear paragraph \
breaks for readability.
5. Never make up policy details, numbers, dates, or eligibility criteria not \
explicitly present in the context.
6. If the user asks about their personal data (leave balance, salary, personal \
schedule, etc.), explain: "I can only provide general policy information. For \
your personal records, please check the HR portal or contact HR directly."
7. Maintain a professional, friendly, and helpful tone.
8. If the confidence is MEDIUM, include this disclaimer at the end: "⚠️ \
Please verify this information with HR as I'm not fully confident in this \
response."
9. Format your answer for readability:
   - Use bullet points for lists
   - Use numbered steps for processes
   - Use paragraphs for explanations
   - Keep paragraphs short (2-3 sentences)
10. If the question is ambiguous, ask for clarification rather than guessing."""


USER_PROMPT_TEMPLATE = """\
CONVERSATION HISTORY:
{conversation_history}

CONTEXT FROM OFFICIAL DOCUMENTS:
---
{retrieved_context}
---

USER QUESTION: {user_query}

{confidence_note}
ASSISTANT RESPONSE:"""


# ---------------------------------------------------------------------------
# Query-rewriting prompts (spec §7)
# ---------------------------------------------------------------------------

REWRITE_SYSTEM_PROMPT = """\
Given the conversation history, rewrite the user's follow-up question into a \
complete, standalone question that includes all necessary context from the \
conversation. Do not answer the question — just rewrite it so it can be \
understood without the conversation history."""


REWRITE_USER_PROMPT = """\
CONVERSATION:
{conversation_history}

FOLLOW-UP: {follow_up_message}

STANDALONE QUESTION:"""


# ---------------------------------------------------------------------------
# Retrieved-context formatting (spec §6.C)
# ---------------------------------------------------------------------------

CONTEXT_CHUNK_TEMPLATE = """\
[Source: {source}, Page {page}, Section: {section}]
{content}
---"""


# ---------------------------------------------------------------------------
# Conversation-history formatting (spec §6.D)
# ---------------------------------------------------------------------------

HISTORY_ENTRY_TEMPLATE = "{role}: {content}"
HISTORY_EMPTY = "No previous conversation."


# ---------------------------------------------------------------------------
# Confidence notes (spec §6.E)
# ---------------------------------------------------------------------------

CONFIDENCE_NOTE_MEDIUM = (
    "Note: I'm not fully confident in the retrieved information for this "
    "question. Include a disclaimer in your response."
)

LOW_CONFIDENCE_DISCLAIMER = (
    "⚠️ Please verify this information with HR as I'm not fully confident "
    "in this response."
)


# ---------------------------------------------------------------------------
# Fallback responses (spec §8)
# ---------------------------------------------------------------------------

HARD_FALLBACK_RESPONSE = """\
I don't have information about that in my knowledge base.

I can help you with questions about:
• Leave policies (annual leave, sick leave, parental leave)
• Remote work guidelines
• Benefits and insurance
• Payroll and compensation
• Company policies and procedures
• Onboarding and offboarding

Is there one of these topics I can help you with? Or you can contact HR \
directly for assistance with your specific question."""


SOFT_FALLBACK_TEMPLATE = """\
I found some related information in my knowledge base, but I couldn't find \
a clear answer to your specific question.

Here's what might be related:
{related_excerpts}

I'd suggest:
• Trying to rephrase your question
• Asking about a specific policy or topic
• Contacting HR directly for personalized assistance

Is there another way I can help you?"""


# ---------------------------------------------------------------------------
# Direct (non-retrieval) responses (spec §9)
# ---------------------------------------------------------------------------

GREETING_TEMPLATE = """\
Hello {user_name}! I'm your HR assistant. I can help you with questions about:
• Company policies and procedures
• Leave and time-off policies
• Benefits and insurance
• Remote work guidelines
• Payroll and compensation

What would you like to know?"""

THANKS_RESPONSE = """\
You're welcome, {user_name}! Let me know if you have any other HR questions — I'm here to help."""

BYE_RESPONSE = """\
Goodbye, {user_name}! Feel free to reach out anytime you have HR questions. Have a great day!"""

GREETING_BACK_RESPONSE = """\
Hello, {user_name}! How can I help you with your HR questions today?"""


BOT_QUESTION_RESPONSE = """\
I'm an AI-powered HR assistant designed to help employees find information \
about company policies, benefits, leave, and other work-related topics.

I work by searching through the company's official documents to find accurate \
answers to your questions. I can't access your personal employee records, but \
I can explain policies and procedures.

How can I help you today?"""


OUT_OF_DOMAIN_RESPONSE = """\
I'm designed specifically to help with HR-related questions. I can assist you \
with topics like:

• Leave policies and time-off requests
• Benefits and insurance coverage
• Remote work guidelines
• Payroll, compensation, and reimbursements
• Company policies and employee handbook

Is there an HR topic I can help you with? If you have a non-HR question, I'd \
recommend reaching out to the appropriate department."""
