import os

from functools import wraps
from flask import g, request, redirect, url_for ,session, render_template

# Decorate routes to require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# Render an error template
def error(message, code=400):
    return render_template("error.html", error=message, error_code=code), code

# Turns a list into a token to user in a full text search
def stringify(list):
    token = ""
    # Get size of list
    size = len(list)
    # Loop through the list
    for x in range(size):
        # If X is first item
        if x == 0:
            token += list[x]["name"]
        # For every item not first or last
        else:
            token += " OR " + list[x]["name"]
    # Return token
    return token

