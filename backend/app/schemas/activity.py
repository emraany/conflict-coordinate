from pydantic import BaseModel


class ActivityType(BaseModel):
    """One ACLED event category recorded in a region during the window.

    Categories are ACLED's own labels, used verbatim — a dot or dossier
    reports what the source coded, never a characterisation of our own.
    """

    type: str
    events: int
    fatalities: int
