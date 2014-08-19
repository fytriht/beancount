"""Everything that relates to creating the Document directives.
"""
import re
import datetime
from os import path
from collections import namedtuple

from beancount.core import account
from beancount.core.data import Source, Document
from beancount.core import data
from beancount.core import getters

__plugins__ = ('process_documents',)


# An error from trying to find the documents.
DocumentError = namedtuple('DocumentError', 'source message entry')


def process_documents(entries, options_map):
    """Check files for document directives and find documents automatically.

    Args:
      entries: A list of all directives parsed from the file.
      options_map: An options dict, as is output by the parser.
        We're using its 'filename' option to figure out relative path to
        search for documents.
    Returns:
      A pair of list of all entries (including new ones), and errors
      generated during the process of creating document directives.
    """
    filename = options_map["filename"]

    # Check that the entries from the input file are okay.
    entries, document_errors = verify_document_entries(entries)

    # Detect filenames that should convert into entries.
    autodoc_entries = []
    autodoc_errors = []
    document_dirs = options_map['documents']
    if document_dirs:
        # Restrict to the list of valid accounts only.
        accounts = getters.get_accounts(entries)

        # Accumulate all the entries.
        for directory in document_dirs:
            new_entries, new_errors = find_documents(directory, filename, accounts)
            autodoc_entries.extend(new_entries)
            autodoc_errors.extend(new_errors)

    # Merge the two lists of entries and errors. Keep the entries sorted.
    entries.extend(autodoc_entries)
    entries.sort(key=data.entry_sortkey)

    return (entries, document_errors + autodoc_errors)


def verify_document_entries(entries):
    """Verify that the document entries point to existing files.

    Args:
      entries: a list of directives whose documents need to be validated.
    Returns:
      The same list of entries, and a list of new errors, if any were encountered.
    """
    errors = []
    for entry in entries:
        if not isinstance(entry, Document):
            continue
        if not path.exists(entry.filename):
            errors.append(
                DocumentError(entry.source,
                              'File does not exist: "{}"'.format(entry.filename),
                              entry))
    return entries, errors


def find_documents(directory, input_filename, accounts_only=None, strict=False):
    """Find dated document files under the given directory.

    If a restricting set of accounts is provided in 'accounts_only', only return
    entries that correspond to one of the given accounts.

    Args:
      directory: A string, the name of the root of the directory hierarchy to be searched.
      input_filename: The name of the file to be used for the Document directives. This is
        also used to resolve relative directory names.
      accounts_only: A set of valid accounts strings to search for.
      strict: A boolean, set to true if you want to generate errors on documents
        found in accounts not provided in accounts_only. This is only meaningful
        if accounts_only is specified.
    Returns:
      A list of new Document objects that were created from the files found, and a list
      of new errors generated.

    """
    errors = []

    # Compute the documents directory name relative to the beancount input
    # file itself.
    if not path.isabs(directory):
        input_directory = path.dirname(input_filename)
        directory = path.abspath(path.normpath(path.join(input_directory,
                                                         directory)))

    # If the directory does not exist, just generate an error and return.
    if not path.exists(directory):
        source = Source(input_filename, 0)
        error = DocumentError(
            source, "Document root '{}' does not exist.".format(directory), None)
        return ([], [error])

    # Walk the hierarchy of files.
    entries = []
    for root, account_name, dirs, files in account.walk(directory):

        # Look for files that have a dated filename.
        for filename in files:
            mo = re.match('(\d\d\d\d)-(\d\d)-(\d\d).(.*)', filename)
            if not mo:
                continue

            # If a restricting set of accounts was specified, skip document
            # directives found in accounts with no corresponding account name.
            if accounts_only and not account_name in accounts_only:
                if strict:
                    if any(account_name.startswith(account) for account in accounts_only):
                        errors.append(DocumentError(
                            Source(input_filename, 0),
                            "Document '{}' found in child account {}.".format(
                                filename, account_name), None))
                    elif any(account.startswith(account_name) for account in accounts_only):
                        errors.append(DocumentError(
                            Source(input_filename, 0),
                            "Document '{}' found in parent account {}.".format(
                                filename, account_name), None))
                continue

            # Create a new directive.
            source = Source(input_filename, 0)
            date = datetime.date(*map(int, mo.group(1, 2, 3)))
            entry = Document(source, date, account_name, path.join(root, filename))
            entries.append(entry)

    return (entries, errors)