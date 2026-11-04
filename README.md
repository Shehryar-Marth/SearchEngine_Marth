# SearchEngine_Marth
docsearch

A small, fast search engine for your own documents. One Python file, no required dependencies.

Ranks results with BM25, the same family of algorithm used by Elasticsearch and Lucene
Shows a snippet for each result with your search terms highlighted
Incremental indexing: re-running only reads new or changed files and removes deleted ones
Works on plain-text files out of the box; PDF and Word support is optional
Requirements
Python 3.8 or newer
Optional, for PDF and Word files:
pip install pypdf python-docx
Quick start
python docsearch.py index ~/Documents      # build the index
python docsearch.py search tax receipts    # search it
python docsearch.py                        # interactive search prompt

Example output:

1. /home/me/Documents/invoice.pdf  (score 2.23)
   **Invoice** for consulting services and **tax** payment
Commands
Command	What it does
index <folder>	Indexes a folder and everything inside it. Safe to re-run; unchanged files are skipped.
search <words>	Prints the top 5 results. Add -n 10 for 10 results.
(no command)	Interactive mode. Type queries; press Enter on an empty line, Ctrl+D, or Ctrl+C to quit.

You can index several folders. They all go into one shared index, and search covers all of them.

Supported files
Type	Extensions	Needs
Text	.txt .md .rst .csv .log .json .html .htm .tex .py .js .yaml .yml	nothing
PDF	.pdf	pypdf
Word	.docx	python-docx

Hidden files and folders (names starting with .) are skipped. Folders you don't have permission to read are skipped with a message.

How it works
Tokenize: text is lowercased and split into words. Common words like "the" and "and" are dropped, and endings are trimmed, so "receipts" matches "receipt".
Index: for each document, the index stores how often each word appears, plus a short text preview (the first 20,000 characters) used for snippets.
Rank: a query is tokenized the same way. Each document is scored with BM25, which rewards documents that contain the query words often, favors rare words over common ones, and doesn't unfairly favor very long documents.

The index is saved to ~/.docsearch_index.json. It is written to a temporary file first and then swapped in, so a crash can't corrupt it.

Configuration

Settings are constants near the top of docsearch.py:

Constant	Default	Meaning
INDEX_FILE	~/.docsearch_index.json	Where the index is stored
TEXT_EXT	see above	Plain-text extensions to index
STOP_WORDS	common English words	Words ignored in documents and queries
SNIPPET_CACHE_CHARS	20000	Preview text kept per document
Troubleshooting

"Index is empty." Run python docsearch.py index <folder> first.

"Skipped .pdf files (run: pip install pypdf python-docx)." Install the optional libraries, then re-run index.

A PDF is indexed but never matches. It is probably a scan (an image of text). Run OCR on it first, for example with ocrmypdf, then re-index.

Snippets are missing or blank. The index was built by an older version of the script. Delete ~/.docsearch_index.json and run index again.

"Warning: ... is unreadable; starting with an empty index." The index file was damaged. Re-run index to rebuild it.

Results from a folder you no longer want. Delete ~/.docsearch_index.json and index only the folders you want.

Limitations
Matches words, not meaning. Searching "car" won't find "automobile".
Simple stemming. "running" won't match "run".
Whole index in memory. Fine for tens of thousands of documents, not millions.
One indexer at a time. Running two index commands simultaneously can overwrite each other's work.
Only the first 20,000 characters of each document are used for snippets. Search still covers the full text.
Tested on Linux only. It should work on Windows and macOS but hasn't been verified there.
Ideas for extending it
Phrase search by storing word positions
Filtering by file type or modification date
A small web interface with Flask or FastAPI
Semantic search using embeddings (sentence-transformers)
OCR for scanned documents