# ===============================================================
# custom_exceptions.py
# Structured exceptions that carry payload to the frontend.
# Rather than surfacing raw ValueErrors, these exceptions include
# the data the frontend needs to render clarification UI.
# ===============================================================


class AmbiguityError(Exception):
    """
    Raised when a title lookup finds more than one candidate.
    Carries the full list of matching titles and the original query
    so the frontend can render a selection prompt.

    entity_key tells the frontend which entity array to override
    when the user picks a candidate ("events", "tasks", "reminders").
    """
    def __init__(self, message: str, candidates: list, query: str, entity_key: str = "events"):
        super().__init__(message)
        self.candidates = candidates   # list of matching title strings
        self.query      = query        # the original search term
        self.entity_key = entity_key   # which entity slot held the ambiguous reference


class SlotConflictError(Exception):
    """
    Raised when CREATE_EVENT detects the requested slot is already booked.
    Carries the requested slot AND the next available suggestion so the
    frontend can offer a one-tap "book this instead" confirmation.

    title is the event that was being scheduled — needed so the frontend
    can include it in the suggested booking confirmation message.
    """
    def __init__(
        self,
        message: str,
        requested_start: str,
        requested_end:   str,
        suggested_start: str = None,
        suggested_end:   str = None,
        title:           str = None,
    ):
        super().__init__(message)
        self.requested_start = requested_start
        self.requested_end   = requested_end
        self.suggested_start = suggested_start
        self.suggested_end   = suggested_end
        self.title           = title