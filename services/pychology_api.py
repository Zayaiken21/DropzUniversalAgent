def get_psychology_data(role):

    # CEO view
    if role == "ceo":
        return {
            "disciplined": 81,
            "fearful": 14,
            "revenge": 5,
            "confidence": 77,
            "notes": [
                "Win rate increases during disciplined sessions.",
                "Avoid revenge trading after consecutive losses.",
                "Confidence highest during London session."
            ]
        }

    # Client view
    elif role == "client":
        return {
            "disciplined": 74,
            "fearful": 19,
            "revenge": 7,
            "confidence": 69,
            "notes": [
                "Strong consistency this week.",
                "Avoid overtrading during volatility spikes."
            ]
        }

    # Fallback
    return {
        "disciplined": 0,
        "fearful": 0,
        "revenge": 0,
        "confidence": 0,
        "notes": []
    }