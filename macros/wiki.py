"""Wiki macros"""

import re
import time
from StringIO import StringIO

from genshi.builder import tag

def title(macro, environ, *args, **kwargs):
    """Return the title of the current page."""

    return environ["page"]["name"]

def add_comment(macro, environ, *args, **kwargs):
    """..."""

    # Prevent multiple inclusions - store a temp in environ
    if "add_comment" in environ:
        raise Exception("add_comment macro cannot be included twice.")
    environ["add_comment"] = True

    # Setup info and defaults
    request = environ["request"]
    user = request.remote.ip
    page = environ["page"]
    page_name = page["name"]
    page_text = page["text"]
    page_url = page["url"]
    
    # Can this user add a comment to this page?
    appendonly = ("appendonly" in args)

    # Get the data from the POST
    comment = request.kwargs.get("comment", "")
    action = request.kwargs.get("action", "")
    
    # Ensure <<add_comment>> is not present in comment, so that infinite
    # recursion does not occur.
    comment = re.sub("(^|[^!])(\<\<add_comment)", "\\1!\\2", comment)
    
    print repr(comment)

    the_preview = None

    # If we are submitting or previewing, inject comment as it should look
    if action == "preview":
        parser = environ["parser"]
        the_preview = tag.div(tag.h1("Preview"), id="preview")
        the_preview += tag.div(parser.generate(comment, environ=environ),
                class_="article")

    # When submitting, inject comment before macro
    if comment and action == "save":
        newtext = ""
        for line in page_text.split("\n"):
            if line.find("<<add_comment") == 0:
                newtext += "==== Comment by %s on %s ====\n%s\n\n" % (
                        user,
                        time.strftime('%c', time.localtime()),
                        comment)
            newtext += line + "\n"

        search = environ["search"]
        storage = environ["storage"]

        storage.reopen()
        search.update()

        storage.save_text(page_name, new_text, user,
                "Comment added by %s" % user)

        search.update_page(name, text=text)

    the_form = tag.form(
            tag.input(type="hidden", name="parent", value=page["node"]),
            tag.fieldset(
                tag.legend("Add Comment"),
                tag.p(
                    tag.textarea((not action == "cancel" and comment or ""),
                        id="comment",
                        name="comment",
                        cols=80, rows=5
                    ),
                    class_="text"
                ),
                tag.h4(tag.label("Your email or username:", for_="author")),
                tag.p(
                    tag.input(id="author", name="author", type="text"),
                    class_="input"
                ),
                tag.p(
                    tag.button("Preview", type="submit",
                        name="action", value="preview"),
                    tag.button("Save", type="submit",
                        name="action", value="save"),
                    tag.button("Cancel", type="submit",
                        name="action", value="cancel"),
                    class_="button"
                ),
            ),
            method="post", action=""
    )

    return tag.div(the_preview, the_form, id="comments")
