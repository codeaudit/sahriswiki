#!/usr/bin/env python

import os
import sys
import tempfile
import optparse
from os import mkdir
from json import dumps, loads
from time import gmtime, strftime
from os.path import join, dirname, exists, abspath

try:
    import psyco
except ImportError:
    psyco = None

os.environ["HGENCODING"] = "utf-8"
os.environ["HGMERGE"] = "internal:merge"

import mercurial.hg
import mercurial.ui
import mercurial.util
import mercurial.revlog
from mercurial.hgweb import hgweb

from circuits import Manager, Debugger
from circuits.net.pollers import Select, Poll

from circuits.web.wsgi import Gateway
from circuits.web.utils import url_quote, url_unquote
from circuits.web import expose, url, Server, Controller, Logger, Static

try:
    from circuits.net.pollers import EPoll
except ImportError:
    EPoll = None

from circuits import __version__ as systemVersion

USAGE = "%prog [options]"
VERSION = "%prog v" + systemVersion

def parse_options():
    """parse_options() -> opts, args

    Parse the command-line options given returning both
    the parsed options and arguments.
    """

    parser = optparse.OptionParser(usage=USAGE, version=VERSION)

    parser.add_option("-b", "--bind",
            action="store", type="string", default="0.0.0.0:8000",
            dest="bind",
            help="Bind to address:[port]")

    parser.add_option("-d", "--data-dir",
            action="store", type="string", default="pages",
            dest="data",
            help="Location of data directory")

    parser.add_option("-n", "--site-name",
            action="store", type="string", default="Test",
            dest="name",
            help="Set site name")

    parser.add_option("-f", "--front-page",
            action="store", type="string", default="FrontPage",
            dest="frontpage",
            help="Set main front page")

    parser.add_option("-e", "--encoding",
            action="store", type="string", default="utf-8",
            dest="encoding",
            help="Set encoding to read and write pages")

    parser.add_option("-r", "--read-only",
            action="store_true", default=False,
            dest="readonly",
            help="Set wiki in read-only mode")

    parser.add_option("", "--jit",
            action="store_true", default=False,
            dest="jit",
            help="Use python HIT (psyco)")

    parser.add_option("", "--multi-processing",
            action="store_true", default=False,
            dest="mp",
            help="Start in multiprocessing mode")

    parser.add_option("", "--poller",
            action="store", type="string", default="select",
            dest="poller",
            help="Specify type of poller to use")

    parser.add_option("", "--debug",
            action="store_true", default=False,
            dest="debug",
            help="Enable debug mode")

    opts, args = parser.parse_args()

    return opts, args

def locked_repo(func):
    """A decorator for locking the repository when calling a method."""

    def new_func(self, *args, **kwargs):
        """Wrap the original function in locks."""

        wlock = self.repo.wlock()
        lock = self.repo.lock()
        try:
            func(self, *args, **kwargs)
        finally:
            lock.release()
            wlock.release()

    return new_func

class WikiStorage(object):
    """
    Provides means of storing wiki pages and keeping track of their
    change history, using Mercurial repository as the storage method.
    """

    def __init__(self, path, charset=None):
        """
        Takes the path to the directory where the pages are to be kept.
        If the directory doen't exist, it will be created. If it's inside
        a Mercurial repository, that repository will be used, otherwise
        a new repository will be created in it.
        """

        self.charset = charset or 'utf-8'
        self.path = path
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        self.repo_path = self._find_repo_path(self.path)
        try:
            self.ui = mercurial.ui.ui(report_untrusted=False,
                                      interactive=False, quiet=True)
        except TypeError:
            # Mercurial 1.3 changed the way we setup the ui object.
            self.ui = mercurial.ui.ui()
            self.ui.quiet = True
            self.ui._report_untrusted = False
            self.ui.setconfig('ui', 'interactive', False)
        if self.repo_path is None:
            self.repo_path = self.path
            create = True
        else:
            create = False
        self.repo_prefix = self.path[len(self.repo_path):].strip('/')
        self.repo = mercurial.hg.repository(self.ui, self.repo_path,
                                            create=create)

    def reopen(self):
        """Close and reopen the repo, to make sure we are up to date."""

        self.repo = mercurial.hg.repository(self.ui, self.repo_path)


    def _find_repo_path(self, path):
        """Go up the directory tree looking for a repository."""

        while not os.path.isdir(os.path.join(path, ".hg")):
            old_path, path = path, os.path.dirname(path)
            if path == old_path:
                return None
        return path

    def _file_path(self, title):
        return os.path.join(self.path, url_quote(title, safe=''))

    def _title_to_file(self, title):
        return os.path.join(self.repo_prefix,
                            url_quote(title, safe=''))

    def _file_to_title(self, filename):
        assert filename.startswith(self.repo_prefix)
        name = filename[len(self.repo_prefix):].strip('/')
        return url_unquote(name)

    def __contains__(self, title):
        return os.path.exists(self._file_path(title))

    def __iter__(self):
        return self.all_pages()

    def merge_changes(self, changectx, repo_file, text, user, parent):
        """Commits and merges conflicting changes in the repository."""

        tip_node = changectx.node()
        filectx = changectx[repo_file].filectx(parent)
        parent_node = filectx.changectx().node()

        self.repo.dirstate.setparents(parent_node)
        node = self._commit([repo_file], text, user)

        partial = lambda filename: repo_file == filename
        try:
            unresolved = mercurial.merge.update(self.repo, tip_node,
                                                True, False, partial)
        except mercurial.util.Abort:
            unresolved = 1, 1, 1, 1
        msg = u'merge of edit conflict'
        if unresolved[3]:
            msg = u'forced merge of edit conflict'
            try:
                mercurial.merge.update(self.repo, tip_node, True, True,
                                       partial)
            except mercurial.util.Abort:
                msg = u'failed merge of edit conflict'
        self.repo.dirstate.setparents(tip_node, node)
        # Mercurial 1.1 and later need updating the merge state
        try:
            mercurial.merge.mergestate(self.repo).mark(repo_file, "r")
        except (AttributeError, KeyError):
            pass
        return msg

    @locked_repo
    def save_file(self, title, file_name, author=u'', comment=u'', parent=None):
        """Save an existing file as specified page."""

        user = author.encode('utf-8') or u'anon'.encode('utf-8')
        text = comment.encode('utf-8') or u'comment'.encode('utf-8')
        repo_file = self._title_to_file(title)
        file_path = self._file_path(title)
        mercurial.util.rename(file_name, file_path)
        changectx = self._changectx()
        try:
            filectx_tip = changectx[repo_file]
            current_page_rev = filectx_tip.filerev()
        except mercurial.revlog.LookupError:
            self.repo.add([repo_file])
            current_page_rev = -1
        if parent is not None and current_page_rev != parent:
            msg = self.merge_changes(changectx, repo_file, text, user, parent)
            user = '<wiki>'
            text = msg.encode('utf-8')
        self._commit([repo_file], text, user)


    def _commit(self, files, text, user):
        try:
            return self.repo.commit(files=files, text=text, user=user,
                                    force=True, empty_ok=True)
        except TypeError:
            # Mercurial 1.3 doesn't accept empty_ok or files parameter
            match = mercurial.match.exact(self.repo_path, '', list(files))
            return self.repo.commit(match=match, text=text, user=user,
                                    force=True)


    def save_data(self, title, data, author=u'', comment=u'', parent=None):
        """Save data as specified page."""

        try:
            temp_path = tempfile.mkdtemp(dir=self.path)
            file_path = os.path.join(temp_path, 'saved')
            f = open(file_path, "wb")
            f.write(data)
            f.close()
            self.save_file(title, file_path, author, comment, parent)
        finally:
            try:
                os.unlink(file_path)
            except OSError:
                pass
            try:
                os.rmdir(temp_path)
            except OSError:
                pass

    def save_text(self, title, text, author=u'', comment=u'', parent=None):
        """Save text as specified page, encoded to charset."""

        data = text.encode(self.charset)
        self.save_data(title, data, author, comment, parent)

    def page_text(self, title):
        """Read unicode text of a page."""

        page = self.open_page(title)
        if page:
            data = page.read()
            text = unicode(data, self.charset, 'replace')
            return text
        else:
            return None

    def page_lines(self, page):
        for data in page:
            yield unicode(data, self.charset, 'replace')

    @locked_repo
    def delete_page(self, title, author=u'', comment=u''):
        user = author.encode('utf-8') or 'anon'
        text = comment.encode('utf-8') or 'deleted'
        repo_file = self._title_to_file(title)
        file_path = self._file_path(title)
        try:
            os.unlink(file_path)
        except OSError:
            pass
        self.repo.remove([repo_file])
        self._commit([repo_file], text, user)

    def open_page(self, title):
        try:
            return open(self._file_path(title), "rb")
        except IOError:
            return None

    def page_file_meta(self, title):
        """Get page's inode number, size and last modification time."""

        try:
            (st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size,
             st_atime, st_mtime, st_ctime) = os.stat(self._file_path(title))
        except OSError:
            return 0, 0, 0
        return st_ino, st_size, st_mtime

    def page_meta(self, title):
        """Get page's revision, date, last editor and his edit comment."""

        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            return None
        rev = filectx_tip.filerev()
        filectx = filectx_tip.filectx(rev)
        date = filectx.date()[0]
        author = unicode(filectx.user(), "utf-8",
                         'replace').split('<')[0].strip()
        comment = unicode(filectx.description(), "utf-8", 'replace')
        return rev, date, author, comment

    def repo_revision(self):
        return self._changectx().rev()

    def page_mime(self, title):
        """Guess page's mime type ased on corresponding file name."""

        file_path = self._file_path(title)
        return page_mime(file_path)


    def _changectx(self):
        """Get the changectx of the tip."""
        try:
            # This is for Mercurial 1.0
            return self.repo.changectx()
        except TypeError:
            # Mercurial 1.3 (and possibly earlier) needs an argument
            return self.repo.changectx('tip')

    def _find_filectx(self, title):
        """Find the last revision in which the file existed."""

        repo_file = self._title_to_file(title)
        changectx = self._changectx()
        stack = [changectx]
        while repo_file not in changectx:
            if not stack:
                return None
            changectx = stack.pop()
            for parent in changectx.parents():
                if parent != changectx:
                    stack.append(parent)
        return changectx[repo_file]

    def page_history(self, title):
        """Iterate over the page's history."""

        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            return
        maxrev = filectx_tip.filerev()
        minrev = 0
        for rev in range(maxrev, minrev-1, -1):
            filectx = filectx_tip.filectx(rev)
            date = filectx.date()[0]
            author = unicode(filectx.user(), "utf-8",
                             'replace').split('<')[0].strip()
            comment = unicode(filectx.description(), "utf-8", 'replace')
            yield rev, date, author, comment

    def page_revision(self, title, rev):
        """Get unicode contents of specified revision of the page."""

        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            return None
        try:
            data = filectx_tip.filectx(rev).data()
        except IndexError:
            return None
        return data

    def revision_text(self, title, rev):
        data = self.page_revision(title, rev)
        text = unicode(data, self.charset, 'replace')
        return text

    def history(self):
        """Iterate over the history of entire wiki."""

        changectx = self._changectx()
        maxrev = changectx.rev()
        minrev = 0
        for wiki_rev in range(maxrev, minrev-1, -1):
            change = self.repo.changectx(wiki_rev)
            date = change.date()[0]
            author = unicode(change.user(), "utf-8",
                             'replace').split('<')[0].strip()
            comment = unicode(change.description(), "utf-8", 'replace')
            for repo_file in change.files():
                if repo_file.startswith(self.repo_prefix):
                    title = self._file_to_title(repo_file)
                    try:
                        version = change[repo_file].filerev()
                    except mercurial.revlog.LookupError:
                        version = -1
                    yield title, version, date, wiki_rev, author, comment

    def all_pages(self):
        """Iterate over the titles of all pages in the wiki."""

        for filename in os.listdir(self.path):
            if (os.path.isfile(os.path.join(self.path, filename))
                and not filename.startswith('.')):
                yield url_unquote(filename)

    def changed_since(self, rev):
        """Return all pages that changed since specified repository revision."""

        last = self.repo.lookup(int(rev))
        current = self.repo.lookup('tip')
        status = self.repo.status(current, last)
        modified, added, removed, deleted, unknown, ignored, clean = status
        for filename in modified+added+removed+deleted:
            if filename.startswith(self.repo_prefix):
                yield self._file_to_title(filename)

class Root(Controller):

    def index(self):
        self.expires(2592000)
        return self.serve_file(abspath("static/index.xhtml"))

    @expose("favicon.ico")
    def favicon(self):
        self.expires(2592000)
        return self.serve_file(abspath("static/favicon.ico"))

    def getip(self):
        self.response.headers["Content-Type"] = "application/javascript"
        return dumps(self.request.remote.ip)

class Wiki(Controller):

    channel = "/wiki"

    def __init__(self, opts):
        super(Wiki, self).__init__()
        self.storage = WikiStorage(opts.data, opts.encoding)

    def Index(self):
        lines = []
        out = lines.append

        out("= Title Index =")
        for name in self.storage:
            out(" * [[%s]]" % name)

        text = "\n".join(lines)

        data = {"success": True,
                "page": {"name": "", "text": text},
                "meta": {"rev": 0, "date": 0, "author": "", "comment": ""},
                "readonly": True,
                "title": "Index of all pargs"
                }

        self.response.headers["Content-Type"] = "application/javascript"
        return dumps(data)

    def History(self, name=None, rev=None):
        lines = []
        out = lines.append

        if name:
            title = "History of \"%s\"" % name
            out("= %s =" % title)
            for rev, date, author, comment in self.storage.page_history(name):
                out(" * [[History/%s/%d|%s]]" % (name, rev,
                    strftime("%Y-%m-%d", gmtime(date))))
                out("[ [[%s|%d]] ] by %s\\\\" % (
                    url(self.request, "/hg/rev/%d" % rev), rev, author))
                out(comment)
            text = "\n".join(lines)
        else:
            title = "Recent Changes"
            out("= %s =" % title)
            for name, ver, date, rev, author, comment in self.storage.history():
                out(" * [[History/%s/%d|%s]] [[%s]]" % (name, rev,
                    strftime("%Y-%m-%d", gmtime(date)), name))
                out("[ [[%s|%d]] ] by %s\\\\" % (
                    url(self.request, "/hg/rev/%d" % rev), rev, author))
                out(comment)
            text = "\n".join(lines)

        data = {"success": True,
                "page": {"name": "", "text": text},
                "meta": {"rev": 0, "date": 0, "author": "", "comment": ""},
                "readonly": True,
                "title":  title
            }

        self.response.headers["Content-Type"] = "application/javascript"
        return dumps(data)

    def GET(self, name="FrontPage", _dc=None):
        if name in self.storage:
            text = self.storage.page_text(name)
            rev, date, author, comment = self.storage.page_meta(name)

            data = {"success": True,
                    "page": {
                        "name": name,
                        "text": text
                        },
                    "meta": {
                        "rev": rev,
                        "date": date,
                        "author": author,
                        "comment": comment
                        }
                    }
        else:
            data = {"success": False,
                    "message": "Page does not exist"}

        self.response.headers["Content-Type"] = "application/javascript"
        return dumps(data)

    def POST(self, name):
        data = loads(self.request.body.read())
        text = data.get("text", "")
        author = data.get("author", "")
        comment = data.get("comment", "")
        self.storage.save_text(name, text, author, comment)
        data = {"success": True, "message": "Page saved successfully"}
        return dumps(data)

def main():
    opts, args = parse_options()

    if opts.jit and psyco:
        psyco.full()

    if ":" in opts.bind:
        address, port = opts.bind.split(":")
        port = int(port)
    else:
        address, port = opts.bind, 8000

    bind = (address, port)

    manager = Manager()

    if opts.debug:
        manager += Debugger()

    poller = opts.poller.lower()
    if poller == "poll":
        Poller = Poll
    elif poller == "epoll":
        if EPoll is None:
            print "No epoll support available - defaulting to Select..."
            Poller = Select
        else:
            Poller = EPoll
    else:
        Poller = Select

    manager += (Server(bind, poller=Poller)
        + Gateway(hgweb(opts.data), "/hg")
        + Static("/js",        docroot="static/js")
        + Static("/css",       docroot="static/css")
        + Static("/images",    docroot="static/images")
        + Static("/templates", docroot="static/templates")
        + Root()
        + Wiki(opts)
        + Logger()
        )

    manager.run()

if __name__ == "__main__":
    main()
