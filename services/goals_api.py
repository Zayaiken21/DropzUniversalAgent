def get_goal_progress(role):

    # CEO can see all goals
    if role == "ceo":
        return [
            {
                "title": "Monthly Profit Goal",
                "progress": 74
            },
            {
                "title": "Consistency Goal",
                "progress": 81
            },
            {
                "title": "Win Rate Goal",
                "progress": 69
            },
            {
                "title": "Funded Challenge",
                "progress": 52
            }
        ]

    # Client goals
    elif role == "client":
        return [
            {
                "title": "Monthly Profit Goal",
                "progress": 62
            },
            {
                "title": "Consistency Goal",
                "progress": 71
            },
            {
                "title": "Win Rate Goal",
                "progress": 58
            }
        ]

    # Fallback
    return []