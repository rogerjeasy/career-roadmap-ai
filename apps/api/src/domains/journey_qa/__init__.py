"""Ask-My-Journey domain — grounded Q&A over the user's own data.

Answers questions like "how's my job search going?" or "what should I focus on
this week?" using only the user's real records — profile, roadmap summary,
applications, evidence, learning, and recent reviews — assembled into context for
the LLM. The answer cites which areas it drew on, and the model is instructed to
say when the data doesn't support an answer rather than speculate. No protected-
attribute inference.
"""
