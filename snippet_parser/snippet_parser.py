from __future__ import unicode_literals

import os
import sys

_upper_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..'))
if _upper_dir not in sys.path:
    sys.path.append(_upper_dir)

import config
from utils import *

import re
import itertools
import wikitools
import mwparserfromhell
import importlib

from base import matches_any, REF_MARKER, CITATION_NEEDED_MARKER

cfg = config.get_localized_config()
WIKIPEDIA_BASE_URL = 'https://' + cfg.wikipedia_domain
WIKIPEDIA_WIKI_URL = WIKIPEDIA_BASE_URL + '/wiki/'
WIKIPEDIA_API_URL = WIKIPEDIA_BASE_URL + '/w/api.php'

STRIP_REGEXP = re.compile( # strip spaces before the markers
    '\s+(' + CITATION_NEEDED_MARKER + '|' + REF_MARKER + ')')

log = Logger()

import os
sys.path.append(os.path.dirname(__file__))
try:
    localized_module = importlib.import_module(cfg.lang_code)
except ImportError:
    log.info('No snippet_parser for lang_code %s, using stub!' % cfg.lang_code)
    localized_module = importlib.import_module('stub')
snippet_parser = localized_module.SnippetParser()

def cleanup_snippet(snippet):
    snippet = re.sub(STRIP_REGEXP, r'\1', snippet).strip()
    snippet = re.sub(',\s+\)', ')', snippet)
    snippet = re.sub('\(\)\s', '', snippet)
    snippet = re.sub('\[\]\s', '', snippet)
    return snippet

def extract_snippets(wikitext, minlen, maxlen):
    snippets = [] # [section, [snippets]]

    sections = mwparserfromhell.parse(wikitext).get_sections(
        include_lead = True, include_headings = True, flat = True)
    assert ''.join(unicode(s) for s in sections) == d(wikitext)

    for i, section in enumerate(sections):
        assert i == 0 or \
            isinstance(section.get(0), mwparserfromhell.nodes.heading.Heading)
        sectitle = unicode(section.get(0).title.strip()) if i != 0 else ''
        secsnippets = []
        snippets.append([sectitle, secsnippets])

        paragraphs = section.split('\n\n')
        for paragraph in paragraphs:
            wikicode = mwparserfromhell.parse(paragraph)

            blacklisted_tag_or_template = itertools.chain(
                (tag.tag in cfg.tags_blacklist
                    for tag in wikicode.filter_tags()),
                (matches_any(tpl, cfg.templates_blacklist)
                    for tpl in wikicode.filter_templates()),
            )
            if any(blacklisted_tag_or_template):
                continue

            snippet = cleanup_snippet(wikicode.strip_code())
            if '\n' in snippet:
                # Lists cause more 'paragraphs' to be generated
                paragraphs.extend(snippet.split('\n'))
                continue

            if CITATION_NEEDED_MARKER not in snippet:
                # marker may have been inside wiki markup
                continue

            usable_len = (
                len(snippet) -
                (len(CITATION_NEEDED_MARKER) *
                    snippet.count(CITATION_NEEDED_MARKER)) -
                (len(REF_MARKER) *
                    snippet.count(REF_MARKER)))
            if usable_len > maxlen or usable_len < minlen:
                continue
            secsnippets.append(snippet)
    return snippets

def extract_lead(wikitext, minlen, maxlen):
    sections = mwparserfromhell.parse(wikitext).get_sections(
        include_lead = True, include_headings = True, flat = True)
    lead = sections[0]

    blacklisted_tag_or_template = itertools.chain(
        (tag.tag in cfg.tags_blacklist
            for tag in lead.filter_tags()),
        (matches_any(tpl, cfg.templates_blacklist)
            for tpl in lead.filter_templates()),
    )
    if any(blacklisted_tag_or_template):
        return []
    lead = cleanup_snippet(lead.strip_code())
    # Take the first paragraph only
    lead = lead.split('\n\n')[0]
    if len(lead) > maxlen or len(lead) < minlen:
        return []
    return [['', [lead]]]

if cfg.lang_code == 'de':
    extract_snippets = extract_lead

if __name__ == '__main__':
    import pprint
    import sys

    title = sys.argv[1]
    wikipedia = wikitools.wiki.Wiki(WIKIPEDIA_API_URL)
    page = wikitools.Page(wikipedia, title)
    wikitext = page.getWikiText()
    pprint.pprint(extract_snippets(wikitext,
        cfg.snippet_min_size, cfg.snippet_max_size))
