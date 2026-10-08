export interface TextStatistics {
  characters: number;
  charactersWithoutSpaces: number;
  words: number;
  chineseCharacters: number;
  letters: number;
  digits: number;
  punctuation: number;
  lines: number;
  nonEmptyLines: number;
  paragraphs: number;
  bytes: number;
}

export interface WordFrequency {
  word: string;
  count: number;
}

export function countText(text: string): TextStatistics {
  const characters = Array.from(text).length;
  const charactersWithoutSpaces = Array.from(text.replace(/\s/g, '')).length;
  const chineseCharacters = (text.match(/[\u4e00-\u9fff]/g) ?? []).length;
  const letters = (text.match(/[A-Za-z]/g) ?? []).length;
  const digits = (text.match(/[0-9]/g) ?? []).length;
  const punctuation = (text.match(/[.,!?;:'"()[\]{}<>，。！？；：、“”‘’（）【】《》—-]/g) ?? [])
    .length;
  const lines = text === '' ? 0 : text.replace(/\r\n?/g, '\n').split('\n').length;
  const lineList = text === '' ? [] : text.replace(/\r\n?/g, '\n').split('\n');
  const nonEmptyLines = lineList.filter((line) => line.trim() !== '').length;
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean).length;
  const words = text.trim() === '' ? 0 : text.trim().split(/\s+/).length;

  return {
    characters,
    charactersWithoutSpaces,
    words,
    chineseCharacters,
    letters,
    digits,
    punctuation,
    lines,
    nonEmptyLines,
    paragraphs,
    bytes: new TextEncoder().encode(text).length,
  };
}

export function wordFrequencies(text: string, limit = 20): WordFrequency[] {
  const tokens = text.toLowerCase().match(/[\u4e00-\u9fff]|[a-z0-9]+/g) ?? [];
  const counts = new Map<string, number>();

  tokens.forEach((token) => {
    counts.set(token, (counts.get(token) ?? 0) + 1);
  });

  return Array.from(counts.entries())
    .map(([word, count]) => ({ word, count }))
    .sort((left, right) => right.count - left.count || left.word.localeCompare(right.word))
    .slice(0, limit);
}
