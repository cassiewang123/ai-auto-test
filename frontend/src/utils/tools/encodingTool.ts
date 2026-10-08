export type EncodingKind =
  | 'base64'
  | 'url'
  | 'hex'
  | 'unicode'
  | 'html';
export type EncodingDirection = 'encode' | 'decode';

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value.trim());
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function toHex(text: string): string {
  return Array.from(new TextEncoder().encode(text))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join(' ');
}

function fromHex(text: string): string {
  const normalized = text.replace(/0x/gi, '').replace(/[^0-9a-f]/gi, '');
  if (normalized.length % 2 !== 0) {
    throw new Error('Hex 字符串长度必须为偶数');
  }
  const bytes = normalized.match(/.{2}/g) ?? [];
  return new TextDecoder().decode(
    new Uint8Array(bytes.map((byte) => Number.parseInt(byte, 16)))
  );
}

function toUnicode(text: string): string {
  return Array.from(text)
    .map((char) => {
      const codePoint = char.codePointAt(0) ?? 0;
      return codePoint > 0xffff
        ? `\\u{${codePoint.toString(16).toUpperCase()}}`
        : `\\u${codePoint.toString(16).toUpperCase().padStart(4, '0')}`;
    })
    .join('');
}

function fromUnicode(text: string): string {
  return text
    .replace(/\\u\{([0-9a-fA-F]+)\}/g, (_, hex: string) =>
      String.fromCodePoint(Number.parseInt(hex, 16))
    )
    .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex: string) =>
      String.fromCharCode(Number.parseInt(hex, 16))
    );
}

function toHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fromHtml(text: string): string {
  return text
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');
}

export function transformText(
  text: string,
  kind: EncodingKind,
  direction: EncodingDirection
): string {
  if (text === '') return '';

  if (kind === 'base64') {
    return direction === 'encode'
      ? bytesToBase64(new TextEncoder().encode(text))
      : new TextDecoder().decode(base64ToBytes(text));
  }
  if (kind === 'url') {
    return direction === 'encode' ? encodeURIComponent(text) : decodeURIComponent(text);
  }
  if (kind === 'hex') {
    return direction === 'encode' ? toHex(text) : fromHex(text);
  }
  if (kind === 'unicode') {
    return direction === 'encode' ? toUnicode(text) : fromUnicode(text);
  }
  return direction === 'encode' ? toHtml(text) : fromHtml(text);
}
