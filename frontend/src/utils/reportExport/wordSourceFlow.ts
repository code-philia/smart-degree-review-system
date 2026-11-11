/** Word-only display text; offsets map original UTF-16 boundaries to display boundaries. */
export function flowWordSourceText(source: string): { text: string; offsets: number[] } {
  const offsets = new Array<number>(source.length + 1);
  let text = '',
    cursor = 0;
  offsets[0] = 0;
  const cjk = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}\u3000-\u303f\uff00-\uffef]/u;
  const word = /[\p{L}\p{N}\p{M}]/u;
  const listStart =
    /^(?:[•●○◦▪▫‣⁃*+\-]\s+|(?:\d{1,3}[.)、](?!\d)|[（(]\d{1,3}[）)]|[一二三四五六七八九十百]+[、.)）]|[（(][一二三四五六七八九十百]+[）)]|[①-⑳])\s*)\S/u;
  while (cursor < source.length) {
    let end = cursor;
    if (/[ \t\r\n]/.test(source[cursor])) while (end < source.length && /[ \t\r\n]/.test(source[end])) end++;
    const whitespace = source.slice(cursor, end);
    const breaks = whitespace.match(/\r\n|\r|\n/g);
    if (breaks) {
      const left = Array.from(source.slice(Math.max(0, cursor - 2), cursor)).at(-1) || '';
      const right = end < source.length ? String.fromCodePoint(source.codePointAt(end)!) : '';
      const nextLine = source.slice(end).split(/[\r\n]/, 1)[0];
      let replacement = '';
      const indent = whitespace.match(/[ \t]*$/)?.[0] || '';
      if (breaks.length > 1) replacement = '\n'.repeat(breaks.length) + indent;
      else if (listStart.test(nextLine)) replacement = '\n' + indent;
      else if (
        left &&
        right &&
        !cjk.test(left) &&
        !cjk.test(right) &&
        !/[-‐‑−]/u.test(left) &&
        ((word.test(left) && word.test(right)) || (/[,.!?;:)]/.test(left) && word.test(right)))
      )
        replacement = ' ';
      offsets[cursor] = text.length;
      text += replacement;
      for (let index = cursor + 1; index <= end; index++) offsets[index] = text.length;
      cursor = end;
    } else {
      offsets[cursor] = text.length;
      const next = end > cursor ? end : cursor + 1;
      const original = cursor,
        base = text.length;
      text += source.slice(cursor, next);
      for (; cursor < next; cursor++) offsets[cursor + 1] = base + cursor + 1 - original;
    }
  }
  return { text, offsets };
}
