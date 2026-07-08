"""Constants for query classification."""

# Valid classification categories
VALID_CLASSIFICATIONS = {
    "greeting_only",
    "bot_question",
    "out_of_domain",
    "follow_up",
    "hr_question",
    "it_question",
}

# Classification → Action mapping
CLASSIFICATION_ACTIONS = {
    "greeting_only": "respond_directly",
    "bot_question": "respond_directly",
    "out_of_domain": "respond_directly",
    "follow_up": "rewrite_then_retrieve",
    "hr_question": "retrieve",
    "it_question": "retrieve",
}

# Direct response templates
DIRECT_RESPONSES = {
    "greeting_only": (
        "Hello! I'm your HR assistant. I can help you with questions about "
        "company policies, leave, benefits, remote work, and more. "
        "What would you like to know?"
    ),
    "bot_question": (
        "I'm an HR assistant bot designed to help employees with questions "
        "about company policies, benefits, leave, and other work-related topics. "
        "I use the company's official documents to provide accurate answers. "
        "How can I help you today?"
    ),
    "out_of_domain": (
        "I'm designed specifically to help with HR-related questions. "
        "I can assist you with topics like leave policies, benefits, "
        "remote work guidelines, payroll, and other company policies. "
        "Is there an HR topic I can help you with?"
    ),
}

# Follow-up reference keywords (for logging/debugging only — LLM does the actual classification)
FOLLOW_UP_INDICATORS = [
    "explain more", "clarify", "elaborate", "tell me more",
    "what about", "and the", "that", "it", "this",
    "above", "previous", "second point", "first point",
    "how do i apply", "how does that work",
]

# -- IT Support contact info (Feature 13) ----------------------------------
IT_SUPPORT_EMAIL = "it-support@company.com"
IT_PORTAL_URL = "https://portal.company.com/it"
IT_HELPDESK_PHONE = "ext. 4357"
