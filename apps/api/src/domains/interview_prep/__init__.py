"""Interview Prep domain — mock interviews + question banks.

Extends the agentic-coach surface with interview practice. Given a target role
(and optional company / job description, grounded in the user's real profile),
it generates a tailored question bank and runs a stateless mock-interview loop:
the LLM plays the interviewer, asks a question, and after each candidate answer
returns scored feedback plus the next question. Completed practices can be saved
with an overall score so the user can track improvement.

Surfaces confidence/feedback honestly and never infers protected attributes.
"""
