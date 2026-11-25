'use strict';

// Small metadata-only parsers. No script execution, DOM, redirects or linked
// resources. The caller binds every response to a fixed authoritative URL.
function risFields(body) {
  if (typeof body !== 'string') return null;
  const fields = {};
  let state = 'before';
  for (const line of body.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const match = /^([A-Z][A-Z0-9])\s{2}-\s?(.*)$/.exec(line);
    if (!match || state === 'after') return null;
    const [, tag, value] = match;
    if (state === 'before') {
      if (tag !== 'TY' || !value.trim()) return null;
      state = 'inside';
    } else if (tag === 'TY') return null;
    if (tag === 'ER') {
      if (value.trim()) return null;
      state = 'after';
    } else (fields[tag] ||= []).push(value.trim());
  }
  return state === 'after' ? fields : null;
}
function arxivHeader(body) {
  if (typeof body !== 'string') return null;
  body = body.replace(/<!--[\s\S]*?(?:-->|$)/g, '');
  // Inert markup cannot establish authorship. Nested templates are deliberately
  // unsupported; ordinary arXiv document headers do not need them.
  if (/<(?:template|plaintext)\b/i.test(body)) return null;
  body = body.replace(/<(script|style|noscript|textarea|title|xmp|iframe|noembed|noframes)\b[^>]*>[\s\S]*?(?:<\/\1\s*>|$)/gi, '');
  const attributes = source => {
    const attrs = {};
    for (const match of source.matchAll(/(?:^|\s)([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g)) {
      const key = match[1].toLowerCase();
      if (!Object.hasOwn(attrs, key)) attrs[key] = match[2] ?? match[3] ?? match[4] ?? '';
    }
    return attrs;
  };
  const hasClass = (attrs, expected) => (attributes(attrs).class || '').split(/\s+/).includes(expected);
  // Consume every complete tag, including quoted attribute values. Scanning
  // only <div> or <span> would also see tag-like text inside another tag's attrs.
  const tags = [...body.matchAll(/<(\/?)([a-z][\w:-]*)\b((?:[^>"']|"[^"]*"|'[^']*')*)>/gi)]
    .map(match => ({ name:match[2].toLowerCase(), close:Boolean(match[1]), attrs:match[3],
      start:match.index, end:match.index + match[0].length }));
  const heading = tags.find(tag => !tag.close && tag.name === 'h1' && hasClass(tag.attrs, 'ltx_title_document'));
  const headingEnd = heading && tags.find(tag => tag.close && tag.name === 'h1' && tag.start >= heading.end);
  const title = headingEnd ? body.slice(heading.end, headingEnd.start) : null;
  const opening = tags.find(tag => !tag.close && tag.name === 'div' && hasClass(tag.attrs, 'ltx_authors'));
  const closing = opening && tags.find(tag => tag.close && tag.name === 'div' && tag.start >= opening.end);
  const block = closing ? body.slice(opening.end, closing.start) : null;
  if (!title || !block || title.length > 4000 || block.length > 16000) return null;
  // Match opening name spans individually so a wrapping creator span cannot
  // swallow its nested person span. Attribute names must be exact, not data-*.
  const names = [...new Set(tags.filter(tag => !tag.close && tag.name === 'span' && tag.start >= opening.end
    && tag.end <= closing.start && hasClass(tag.attrs, 'ltx_personname')).map(tag => {
      const end = tags.find(next => next.close && next.name === 'span' && next.start >= tag.end && next.start <= closing.start);
      return end ? body.slice(tag.end, end.start) : '';
    }).filter(Boolean))];
  const identity = tags.filter(tag => !tag.close && tag.name === 'meta').map(tag => {
    const attrs = attributes(tag.attrs);
    return attrs.name?.toLowerCase() === 'citation_arxiv_id' ? attrs.content : null;
  }).find(Boolean);
  return names.length ? { title, authors: names.slice(0, 30), identity } : null;
}
module.exports = { risFields, arxivHeader };
