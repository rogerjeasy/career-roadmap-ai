"""Exports domain — portable copies of the user's plan.

Renders a roadmap as Markdown (easy to paste anywhere) or as an iCalendar
(``.ics``) file whose phases lay out sequentially from today, so the plan drops
straight into Google/Apple/Outlook calendars. Pure string generators keep this
dependency-free and unit-testable.
"""
