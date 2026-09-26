# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "paddock"
copyright = "2026 Phoenix Zerin"
author = "Phoenix Zerin"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.napoleon",
]

# ADRs, deferred features and plans are for contributors and coding agents,
# read on GitHub; only the user-facing pages are published.
exclude_patterns = [
    ".DS_Store",
    "Thumbs.db",
    "_build",
    "adr",
    "future",
    "superpowers",
]

language = "en-nz"

# Report unresolved Python cross-references, which -W then fails the build on
nitpicky = True

source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"

# -- Options for autosectionlabel extension ----------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/autosectionlabel.html#configuration
# Prefixing with the document name keeps same-titled sections on different
# pages from colliding into duplicate-label warnings.
autosectionlabel_prefix_document = True

# -- Options for autodoc extension -------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#configuration
autoclass_content = "both"
autodoc_default_options = {
    "member-order": "alphabetical",
    "members": True,
    "special-members": False,
    "undoc-members": True,
}

# -- Options for MyST parser -------------------------------------------------
# https://myst-parser.readthedocs.io/en/latest/configuration.html
# Generates anchors for headings down to h3, so Markdown links such as
# `[precedence](#precedence)` resolve as they do on GitHub.
myst_heading_anchors = 3

# -- Options for napoleon extension ------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#configuration
napoleon_attr_annotations = True
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
