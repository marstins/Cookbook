import sqlite3
import os

from helpers import login_required, error, stringify
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

# Configure application
app = Flask(__name__)
# Ensure templates auto reload
app.config["TEMPLATES_AUTO_RELOAD"] = True
# Declare database name
db = "cookbook.db"

# Configure session to use filesystem
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


# Home page showing user's pantry(owned items)
@app.route("/", methods=["POST", "GET"])
@login_required
def index():
    # If request was sent via form
    # Add item to pantry
    if request.method == "POST":
        # Check for added item by user
        added_item = request.form.get("item")
        added_item = added_item.lower()
        
        # If user failed to provide an item, return error
        if not added_item:
            return error("please input an item", 403)

        # Query database to see if added item already exists in items table
        all_items = query(db, "SELECT * FROM items WHERE name = ?", (added_item,))

        # If the item does not exist in the items table, add it
        if len(all_items) != 1:
            query(db, "INSERT INTO items (name) VALUES (?)", (added_item,))

        # Query database to see if user already has the item in their pantry
        items = query(db, "SELECT * FROM items WHERE name = ?", (added_item,))
        has_item = query(db, "SELECT * FROM pantry WHERE user_id = ? AND item_id = ?", (session["user_id"], items[0]["id"],))
        
        # If user has item, flash message warning that user already has the item and redirect to index
        if has_item:
            flash("You already own that item!")
            return redirect("/")
        
        # Else, insert item into user's pantry
        query(db, "INSERT INTO pantry (user_id, item_id) VALUES (?, ?)", (session["user_id"], items[0]["id"],))

        # Flash message confirming operation
        flash("Item added!")
        return redirect("/")
    
    # If request was via redirect or link
    else:
        # Query database for user's items and redirect to index
        pantry = query(db, "SELECT * FROM items JOIN pantry ON items.id = pantry.item_id WHERE pantry.user_id = ?", (session["user_id"],))
        
        # If user has no items in their pantry, render template with message
        if not pantry:
            message = "You don't have any item in you pantry ):"
            return render_template("index.html", message=message)
        # Else, render template with pantry items
        return render_template("index.html", pantry=pantry)     


# Remove item from pantry
@app.route("/remove_item", methods=["POST"])
@login_required
def remove_item():
    # Check the item removed by user
    removed_item = request.form.get("removed_item")
    # Query the database and remove item from user's pantry
    query(db, "DELETE FROM pantry WHERE user_id = ? and item_id = ?", (session["user_id"], removed_item,))

    # Flash message confirming operation and redirect to index
    flash("Item removed!")
    return redirect("/")


# Page containing user's saved recipes
@app.route("/cookbook", methods=["POST", "GET"])
@login_required
def cookbook():  
    # If request was sent via form
    # Search cookbook for saved recipes
    if request.method == "POST":
        # Get entries to search for
        parameters = request.form.get("parameters")
        # Estabilish a separator to use during query
        separator = " OR "
        # Separate full search input into a list
        token = parameters.split(" ")
        # Join the list using the separator between elements
        token = separator.join(token)
        
        # Store cookbook token in session
        session["cookbook_token"] = token
        # If user failed to provide entries, return error
        if not parameters:
            return error("please input something to search", 403) 

        # Else, renderirect to cookbook searched
        return redirect("/cookbook_searched")
    
    # If request was via redirect or link
    else:
        # Reset cookbook_token in session to false
        session["cookbook_token"] = False
        # Query database for recipes in user's cookbook
        recipes = query(db, "SELECT * FROM recipes JOIN favourites ON recipes.id = favourites.recipe_id WHERE favourites.user_id = ? ORDER BY recipes.name", (session["user_id"],))
        
        # If user has no recipe in cookbook, render a message
        if not recipes:
            message = "You don't have any recipe in your cookbook ):"
            return render_template("cookbook.html", message=message)
        # Else, render template with cookbook recipes
        return render_template("cookbook.html", recipes=recipes)


# Search and render results in cookbook result page
@app.route("/cookbook_searched")
@login_required
def cookbook_searched():
    # Query database for existing recipes in user's cookbook that match the search entries
    recipes = query(db, "SELECT * FROM recipes_fts JOIN favourites ON recipes_fts.id = favourites.recipe_id WHERE recipes_fts MATCH ? AND favourites.user_id = ? ORDER BY recipes_fts.name", (session["cookbook_token"], session["user_id"],)) 
    
    # If no recipes match query, render cookbook template and show message in the page
    if len(recipes) == 0:
        message = "Could not find any recipes matching your search ):"
        return render_template("cookbook_results.html", message=message)

    # Else, render template with search results
    return render_template("cookbook_results.html", recipes=recipes)


# Remove recipe from cookbook
@app.route("/remove_recipe", methods=["POST", "GET"])
@login_required
def remove_recipe():
    # Check recipe removed by user
    removed_recipe = request.form.get("removed_recipe")
    # Delete recipe from user's cookbook
    query(db, "DELETE FROM favourites WHERE user_id = ? AND recipe_id = ?", (session["user_id"], removed_recipe,))

    # Check if recipe was marked as private
    is_private = query(db, "SELECT * FROM recipes WHERE id = ?", (removed_recipe,))
    
    # If recipe is private, delete from recipes table, since the creator has no need for it, and no other user can access it
    if is_private[0]["status"] == "private":
        query(db, "DELETE FROM recipes WHERE id = ?", (removed_recipe,))
    
    # Flash message confirming operation
    flash("Recipe removed!")
    # If operation was realized before any search operation, redirect to cookbook
    if not session["cookbook_token"]:
        return redirect("/cookbook")
    # Else, redirect to search page with results
    else:
        return redirect("/cookbook_searched")


# Page containing form for creating new recipe
@app.route("/create_recipe", methods=["POST", "GET"])
@login_required
def create_recipe():
    # If request was sent via form
    # Create new recipe
    if request.method == "POST":
        # Check for recipe name
        name = request.form.get("name")
        # Check for recipe ingredients
        ingredients = request.form.get("ingredients")
        # Check for recipe instructions
        instructions = request.form.get("instructions")
        # Check for recipe status
        status = request.form.get("status")
        
        # If user did not check "public", consider recipe as private
        if not status:
            status = "private"
        # Store the username of recipe creator
        creator = session["username"]
        
        # If user failed to provide a name, return error
        if not name:    
            return error("please input a name", 403)
        # If user failed to provide ingredients, return error
        elif not ingredients:
            return error("please input the ingredients", 403)
        # If user failed to provide instructions, return error
        elif not instructions:
            return error("please input the instructions", 403)

        # Query database and insert new recipe into recipes table
        query(db, "INSERT INTO recipes (name, ingredients, instructions, status, creator) VALUES (?, ?, ?, ?, ?)", (name, ingredients, instructions, status, creator,))
        # Query database for new recipe's id
        recipe = query(db, "SELECT * FROM recipes WHERE name = ? AND ingredients = ? AND instructions = ?", (name, ingredients, instructions,))
        # Query database and insert new recipe into user's cookbook
        query(db, "INSERT INTO favourites (user_id, recipe_id) VALUES (?, ?)", (session["user_id"], recipe[0]["id"],))

        # Flash message confirming operation and render page's template
        flash("Recipe created!")
        return render_template("/create_recipe.html")
    # If request was via redirect or link
    else:
        # Render page's template
        return render_template("create_recipe.html")


# Page containing recipes that can be made with user's pantry
@app.route("/can_cook")
@login_required
def can_cook():
    # Query database for user's pantry items
    ingredients = query(db, "SELECT items.* FROM items JOIN pantry ON items.id = pantry.item_id WHERE pantry.user_id = ?", (session["user_id"],))
    
    # If user has no ingredients in pantry
    if not ingredients:
        message = "You don't have anything in your pantry to cook with ):"
        return render_template("can_cook.html", message=message)
    
    # Turn ingredients list into a token
    token = stringify(ingredients)

    # Query database for recipes in user's cookbook that contain user's pantry item
    recipes = query(db, "SELECT * FROM recipes_fts JOIN favourites ON recipes_fts.id = favourites.recipe_id WHERE recipes_fts MATCH ? AND favourites.user_id = ? ORDER BY recipes_fts.name", (token, session["user_id"],))
    
    # If there are no matching recipes, return message and render page's template
    if not recipes:
        message = "You can't cook anything with the items in your pantry ):"
        return render_template("can_cook.html", message=message)
    # Else, render page's template with matching recipes
    return render_template("can_cook.html", recipes=recipes)


# Page to search for public recipes
@app.route("/search_recipes", methods=["POST", "GET"])
@login_required
def search_recipes():
    # If request was sent via form
    # Format search parameters and redirect to results page
    if request.method == "POST":
        # Get entries to search for
        parameters = request.form.get("parameters")
        # Estabilish a separator to use during query
        separator = " OR "
        # Separate full search input into a list
        token = parameters.split(" ")
        # Join the list using the separator between elements
        token = separator.join(token)
        # # Keep track of user's username
        # creator = session["username"]
        is_created = request.form.get("created")
       
        # If user failed to provide entries, return error
        if not parameters:
            return error("please input something to search", 403)

        # Store the search token in the session
        session["search_token"] = token
        # Store the user's preference regarding who created the recipe in the session
        if is_created:
            session["is_created"] = True
        else:
            session["is_created"] = False
        return redirect("/searched")
    # If request was via redirect or link
    else:
        # Render page template
        return render_template("search.html")


# Search and render results in result page
@app.route("/searched")
@login_required
def searched():
    # If user checked box to search for recipes of their own creation
    if session["is_created"]:
        # Query database for all public recipes in the database matching search entries not created by user
        recipes = query(db, "SELECT * FROM recipes_fts WHERE recipes_fts MATCH ? AND status = 'public' AND NOT id IN (SELECT recipe_id FROM favourites WHERE user_id = ?) ORDER BY recipes_fts.name", (session["search_token"], session["user_id"],))
    # If user only wants recipes not created by themselves
    else:
        # Query database for all public recipes in the database matching search entries not created by user
        recipes = query(db, "SELECT * FROM recipes_fts WHERE recipes_fts MATCH ? AND status = 'public' AND NOT creator = ? AND NOT id IN (SELECT recipe_id FROM favourites WHERE user_id = ?) ORDER BY recipes_fts.name", (session["search_token"], session["username"], session["user_id"],))
    
    # If there are no matching recipes, render template with message
    if len(recipes) == 0:
        message = "Could not find any recipes matching your search ):"
        return render_template("search_results.html", message=message)
    
    # Else, render page with matched recipes
    return render_template("search_results.html", recipes=recipes)


# Add recipe to cookbook
@app.route("/add_recipe", methods=["POST", "GET"])
@login_required
def add_recipe():
    # Check recipe added by user
    added_recipe = request.form.get("added_recipe")
    # Query database and insert recipe into users cookbook
    query(db, "INSERT INTO favourites (user_id, recipe_id) VALUES (?, ?)", (session["user_id"], added_recipe,))

    # Flash message confirming operation and redirect to searched to prevent reseting search results
    flash("Recipe added to cookbook!")
    return redirect("/searched")   


# Login page
@app.route("/login", methods=["POST", "GET"])
def login():
    # Clear session
    session.clear()

    # If request was sent via form
    # Log user in
    if request.method == "POST":
        # Get typed username
        username = request.form.get("username")
        # Get typed password
        password = request.form.get("password")

        # If user fail to provide an username, return error
        if not username:
            return error("please input an username", 403)
        # If user fail to provide a password, return error
        elif not password:
            return error("please input a password", 403)

        # Query database for user's username
        user = query(db, "SELECT * FROM users WHERE username = ?", (username,))
        
        # If there is no username, or the passwords do not match, return error
        if len(user) != 1 or not check_password_hash(user[0]["password"], password):
            return error("incorrect username/password", 403)

        # Store user id in session 
        session["user_id"] = user[0]["id"]
        # Store user username in session
        session["username"] = user[0]["username"]

        # Flash message confirming operation and redirect to index
        flash("You've logged in!")
        return redirect("/")

    # If request was via redirect or link
    else:
        # Render login page template
        return render_template("login.html")


# Log user out
@app.route("/logout")
def logout():
    # Clear session
    session.clear()
    # Flash message confirming operation and render login page template
    flash("You've logged out!")
    return render_template("login.html")


# Register page
@app.route("/register", methods=["POST", "GET"])
def register():
    # If request was sent via form
    # Register new user
    if request.method == "POST":
        # Get typed username
        username = request.form.get("username")
        # Get type password
        password = request.form.get("password")
        # Get typed password confirmation
        confirmation = request.form.get("confirmation")
        
        # If user fail to provide an username, return error
        if not username:
            return error("please input an username", 400)
        # If user fail to provide a password, return error
        elif not password:
            return error("please input a password", 400)
        # If user fail to provide a password confirmation, return error
        elif not confirmation:
            return error("please confirm your password", 400)
        # If password and password confirmation do not match, return error
        elif password != confirmation:
            return error("passwords do not match", 400)

        # Query database to see if username already exists
        user = query(db, "SELECT * FROM users WHERE username = ?", (username,))
        # If username already exists, return error
        if len(user) != 0:
            return error("username already in use", 400)

        # Query database and insert new user
        query(db, "INSERT INTO users (username, password) VALUES (?, ?)", (username, generate_password_hash(password),))

        # Flash message confirming operation and redirect to login page
        flash("User registered!")
        return render_template("login.html")
    # If request was via redirect or link
    else:
        # Render register page template
        return render_template("register.html")


# Handle error
def errorhandler(e):
    if not isinstance (e, HTTPException):
        e = InternalServerError()
    return error(e.name, e.code)

# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

# Query database
def query(db, sql, values):
    # Connect to database
    con = sqlite3.connect(db, check_same_thread=False) 
    # Create factory to return dictionary rows
    con.row_factory = sqlite3.Row
    with con:
        # Create cursor for database connection
        cur = con.cursor()
        # Execute query
        cur.execute(sql, values)
        # Store all rows in answer
        answer = cur.fetchall()
    # If connection to database is still open, close it and release cursor
    if con:
        con.close()
    # Return answer
    return answer