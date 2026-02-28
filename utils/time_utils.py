from datetime import datetime

def get_local_time():
    """
    Returns the current local time string, including day of the week and date.
    """
    now = datetime.now()
    return now.strftime("%A, %B %d, %Y - %I:%M %p")