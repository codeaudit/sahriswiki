.. _sahriswiki Website: http://sahriswiki.org/
.. _circuits: https://github.com/circuits/circuits/
.. _sahriswiki Page on PyPi: http://pypi.python.org/pypi/sahriswiki
.. _MIT License: http://www.opensource.org/licenses/mit-license.php
.. _Create an Issue: https://github.com/prologic/sahriswiki/issue/new
.. _sahriswiki Downloads page: https://github.com/prologic/sahriswiki/downloads


sahriswiki
==========

.. image:: https://badge.waffle.io/prologic/sahriswiki.png?label=ready&title=Ready 
   :target: https://waffle.io/prologic/sahriswiki
   :alt: 'Stories in Ready'

sahriswiki is a **lightweight** **Wiki Engine** built using the
`circuits`_ and circuits.web framework framework, is modular, pluggable
and themeable.

sahriswiki aims to implement a core set of features that are a mixture
of "best of breed" Wiki, Blog, and CMS features.

**Website**: http://sahriswiki.org/

**Documentation**: http://sahriswiki.org/Docs/

**Project website**: https://github.com/prologic/sahriswiki/

**PyPI page**: http://pypi.python.org/pypi/sahriswiki


Features
--------

- small and lightweight
- mercurial storage engine
- plugin architecture


Requirements
------------

sahriswiki depends on the following software:

- `circuits`_
- `Mercurial <http://mercurial.selenic.com/>`_
- `SQLAlchemy <http://www.sqlalchemy.org/>`_
- `creoleparser <http://code.google.com/p/creoleparser/>`_
- `genshi <http://genshi.edgewall.org/>`_
- `feedformatter <http://code.google.com/p/feedformatter/>`_


Quick Start with Docker
-----------------------

You can easily and quickly spin up an instance of the SahrisWiki Engine
using `Docker <https://www.docker.com>`_ by simply running::
    
    $ docker run -p 80:80 prologic/sahriswiki
    
This image is an Automated Build available on the
`Docker Hub <https://hub.docker.com>`_
`prologic/sahriswiki <https://hub.docker.com/r/prologic/sahriswiki>`_.


Installation
------------

The simplest and recommended way to install sahriswiki is with pip.
You may install the latest stable release from PyPI with pip::
    
    $ pip install sahriswiki
    
Alternatively, you may download the source package from the
`sahriswiki Page on PyPi`_ or the `sahriswiki Downloads page`_ on the
`sahriswiki Website`_; extract it and install using::

    > python setup.py install


License
-------

sahriswiki is licensed under the `MIT License`_.


Feedback
--------

I welcome any questions or feedback about bugs and suggestions on how to 
improve sahriswiki. Let me know what you think about sahriswiki.
I am on twitter `@therealprologic <http://twitter.com/therealprologic>`_.

Do you have suggestions for improvement? Then please `Create an Issue`_
with details of what you would like to see. I'll take a look at it and
work with you to either incorporate the idea or find a better solution.
